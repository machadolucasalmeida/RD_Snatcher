import re
import requests
import time
import os
import threading
from rich.console import Console
from rich.live import Live
from rich.table import Table

# === CONFIG HERE ===
RD_TOKEN = 'TI7IARLHWX7SD37EAVNVOBQ4QRA46XGXRVLXRTAWI223RWVYFOMA'
QBIT_HOST = 'http://localhost:8080'
QBIT_USER = 'machadolucas'
QBIT_PASS = 'Machado@Lucas157525#@$'
SAVE_PATH = r'C:\media\Downloads'
SONARR_API_KEY = 'fffba156ea23425e89e43e3da4d27fa8'
SONARR_HOST = 'http://localhost:8989'
CHECK_INTERVAL = 5
DOWNLOAD_CHUNK_SIZE = 8192
# ====================

session = requests.Session()
console = Console()
downloads = []
sent_magnets = set()

if not os.path.exists(SAVE_PATH):
    os.makedirs(SAVE_PATH)

def extract_episode_info(filename):
    match = re.search(r'[Ss](\d{2})[Ee](\d{2})', filename)
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
        return season, episode
    return None, None

def trigger_sonarr_rescan():
    try:
        res = requests.post(f"{SONARR_HOST}/api/command", json={"name": "RescanSeries"},
                            headers={"X-Api-Key": SONARR_API_KEY})
        if res.status_code == 201:
            console.log("🔁 Triggered Sonarr Rescan")
        else:
            console.log(f"⚠️ Failed to trigger Sonarr rescan: {res.text}")
    except Exception as e:
        console.log(f"❌ Sonarr rescan error: {e}")

def login_qbittorrent():
    r = session.post(f"{QBIT_HOST}/api/v2/auth/login",
                     data={'username': QBIT_USER, 'password': QBIT_PASS})
    if 'Ok.' not in r.text:
        console.log('❌ Failed to login to qBittorrent')
        exit()
    else:
        console.log('✅ Logged in to qBittorrent')

def get_torrents():
    r = session.get(f"{QBIT_HOST}/api/v2/torrents/info")
    return r.json()

class DownloadTask:
    def __init__(self, filename, url, save_path):
        self.filename = filename
        self.url = url
        self.save_path = save_path
        self.progress = 0
        self.total_length = 0
        self.status = "waiting"
        self.thread = threading.Thread(target=self.download)
        self._pause = threading.Event()
        self._pause.set()
        self._stop = threading.Event()

    def start(self):
        self.status = "downloading"
        self.thread.start()

    def download(self):
        try:
            unrestrict_r = requests.post(
                'https://api.real-debrid.com/rest/1.0/unrestrict/link',
                headers={'Authorization': f'Bearer {RD_TOKEN}'},
                data={'link': self.url}
            )
            if unrestrict_r.status_code != 200:
                console.log(f'❌ Failed to unrestrict {self.filename}: {unrestrict_r.text}')
                self.status = "error"
                return

            unrestricted_data = unrestrict_r.json()
            unrestricted_url = unrestricted_data['download']
            correct_filename = unrestricted_data.get('filename', self.filename)
            season, _ = extract_episode_info(correct_filename)
            series_name = correct_filename.split('.')[0].replace('-', ' ').replace('_', ' ').title()

            if season:
                folder_path = os.path.join(SAVE_PATH, series_name, f"Season {season}")
            else:
                folder_path = os.path.join(SAVE_PATH, series_name)
            os.makedirs(folder_path, exist_ok=True)

            self.save_path = os.path.join(folder_path, correct_filename)
            self.filename = correct_filename

            r = requests.get(unrestricted_url, stream=True)
            self.total_length = int(r.headers.get('content-length', 0))
            if self.total_length == 0:
                console.log(f'❌ No content to download for {self.filename}')
                self.status = "error"
                return

            with open(self.save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if self._stop.is_set():
                        console.log(f"Stopped {self.filename}")
                        return
                    while not self._pause.is_set():
                        time.sleep(0.1)
                    if chunk:
                        f.write(chunk)
                        self.progress += len(chunk)

            self.status = "finished"
            console.log(f"✅ Downloaded and saved: {self.save_path}")

        except Exception as e:
            console.log(f"❌ Error downloading {self.filename}: {e}")
            self.status = "error"

    def pause(self):
        self._pause.clear()
        self.status = "paused"

    def resume(self):
        self._pause.set()
        self.status = "downloading"

    def stop(self):
        self._stop.set()
        if os.path.exists(self.save_path):
            os.remove(self.save_path)
        self.status = "cancelled"

def send_to_rd(magnet, torrent_hash):
    r = requests.post(
        'https://api.real-debrid.com/rest/1.0/torrents/addMagnet',
        headers={'Authorization': f'Bearer {RD_TOKEN}'},
        data={'magnet': magnet}
    )
    if r.status_code == 201:
        console.log('✅ Sent to Real-Debrid:', magnet)
        rd_id = r.json()['id']

        select_r = requests.post(
            f'https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{rd_id}',
            headers={'Authorization': f'Bearer {RD_TOKEN}'},
            data={'files': 'all'}
        )
        if select_r.status_code == 204:
            console.log('✅ Selected all files automatically')

        session.post(f"{QBIT_HOST}/api/v2/torrents/delete", data={
            'hashes': torrent_hash,
            'deleteFiles': True
        })

        wait_and_create_download_task(rd_id)
    else:
        console.log('❌ Failed to send to Real-Debrid:', r.text)

def wait_and_create_download_task(rd_id):
    console.log('⏳ Waiting for caching...')
    for _ in range(40):
        status_r = requests.get(f'https://api.real-debrid.com/rest/1.0/torrents/info/{rd_id}',
                                headers={'Authorization': f'Bearer {RD_TOKEN}'})
        if status_r.status_code == 200:
            status = status_r.json()
            if status['status'] == 'downloaded':
                console.log('✅ Torrent is cached!')
                for link in status['links']:
                    filename = link.split('/')[-1].split('?')[0]
                    dummy_path = os.path.join(SAVE_PATH, filename)
                    task = DownloadTask(filename, link, dummy_path)
                    downloads.append(task)
                    task.start()
                trigger_sonarr_rescan()
                break
        time.sleep(CHECK_INTERVAL)

def make_table():
    table = Table(title="Real-Debrid Downloads")
    table.add_column("ID", style="cyan")
    table.add_column("Filename", style="magenta")
    table.add_column("Progress", style="green")
    table.add_column("Status", style="yellow")
    for i, task in enumerate(downloads):
        size = os.path.getsize(task.save_path) if os.path.exists(task.save_path) else 0
        percent = (task.progress / size * 100) if size > 0 else 0
        table.add_row(str(i), task.filename, f"{percent:.2f}%", task.status)
    return table


def main_loop():
    with Live(make_table(), refresh_per_second=2) as live:
        while True:
            live.update(make_table())
            time.sleep(1)

def user_controls():
    while True:
        command = input("\nEnter command (pause [id], resume [id], cancel [id]): ").strip().split()
        if len(command) != 2:
            continue
        action, idx = command
        try:
            idx = int(idx)
            task = downloads[idx]
            if action == "pause":
                task.pause()
            elif action == "resume":
                task.resume()
            elif action == "cancel":
                task.stop()
        except Exception as e:
            console.log(f"Error: {e}")

if __name__ == "__main__":
    threading.Thread(target=main_loop, daemon=True).start()
    threading.Thread(target=user_controls, daemon=True).start()
    login_qbittorrent()

    while True:
        torrents = get_torrents()
        for torrent in torrents:
            if torrent['state'] in ('metaDL', 'stalledDL', 'downloading'):
                hash_ = torrent['hash']
                magnet = f'magnet:?xt=urn:btih:{hash_}'
                if magnet not in sent_magnets:
                    send_to_rd(magnet, hash_)
                    sent_magnets.add(magnet)
        time.sleep(CHECK_INTERVAL)
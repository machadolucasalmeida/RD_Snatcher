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
CHECK_INTERVAL = 5  # seconds
DOWNLOAD_CHUNK_SIZE = 8192
# ====================

session = requests.Session()
console = Console()
downloads = []

if not os.path.exists(SAVE_PATH):
    os.makedirs(SAVE_PATH)

class DownloadTask:
    def __init__(self, filename, url, save_path):
        self.filename = filename
        self.url = url
        self.save_path = save_path
        self.progress = 0
        self.total_length = 0
        self.status = "waiting"
        self.thread = threading.Thread(target=self.download)

    def start(self):
        self.status = "downloading"
        self.thread.start()

    def download(self):
        try:
            # Unrestrict link
            unrestrict_r = requests.post(
                'https://api.real-debrid.com/rest/1.0/unrestrict/link',
                headers={'Authorization': f'Bearer ' + RD_TOKEN},
                data={'link': self.url}
            )
            if unrestrict_r.status_code != 200:
                console.log(f'❌ Failed to unrestrict {self.filename}: {unrestrict_r.text}')
                self.status = "error"
                return

            unrestricted_data = unrestrict_r.json()
            unrestricted_url = unrestricted_data['download']
            correct_filename = unrestricted_data.get('filename', self.filename)
            console.log(f'✅ Unrestricted and got filename: {correct_filename}')

            # Update save_path with the correct filename
            folder_path = os.path.dirname(self.save_path)
            self.save_path = os.path.join(folder_path, correct_filename)
            self.filename = correct_filename  # Update for UI progress display

            # Start downloading
            r = requests.get(unrestricted_url, stream=True)
            self.total_length = int(r.headers.get('content-length', 0))
            if self.total_length == 0:
                console.log(f'❌ No content to download for {self.filename}')
                self.status = "error"
                return

            with open(self.save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        self.progress += len(chunk)

            self.status = "finished"

        except Exception as e:
            console.log(f"❌ Error downloading {self.filename}: {e}")
            self.status = "error"


def make_table():
    table = Table(title="Real-Debrid Downloads")
    table.add_column("ID", style="cyan")
    table.add_column("Filename", style="magenta")
    table.add_column("Progress", style="green")
    table.add_column("Status", style="yellow")
    for i, task in enumerate(downloads):
        if task.total_length > 0:
            percent = (task.progress / task.total_length) * 100
        else:
            percent = 0
        table.add_row(str(i), task.filename, f"{percent:.2f}%", task.status)
    return table

def main_loop():
    with Live(make_table(), refresh_per_second=2) as live:
        while True:
            live.update(make_table())
            time.sleep(1)

def login_qbittorrent():
    r = session.post(QBIT_HOST + '/api/v2/auth/login', data={'username': QBIT_USER, 'password': QBIT_PASS})
    if 'Ok.' not in r.text:
        console.log('❌ Failed to login to qBittorrent')
        exit()
    else:
        console.log('✅ Logged in to qBittorrent')

def get_torrents():
    r = session.get(QBIT_HOST + '/api/v2/torrents/info')
    return r.json()

def send_to_rd(magnet, torrent_hash):
    r = requests.post(
        'https://api.real-debrid.com/rest/1.0/torrents/addMagnet',
        headers={'Authorization': f'Bearer {RD_TOKEN}'},
        data={'magnet': magnet}
    )
    if r.status_code == 201:
        console.log('✅ Sent to Real-Debrid:', magnet)
        rd_id = r.json()['id']

        # Auto-select all files
        select_url = f'https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{rd_id}'
        select_data = {'files': 'all'}
        select_r = requests.post(select_url, headers={'Authorization': f'Bearer {RD_TOKEN}'}, data=select_data)
        if select_r.status_code == 204:
            console.log('✅ Selected all files automatically')
        else:
            console.log('⚠️ Failed to select files:', select_r.text)

        # Delete torrent from qBittorrent
        delete_url = f"{QBIT_HOST}/api/v2/torrents/delete"
        delete_data = {'hashes': torrent_hash, 'deleteFiles': True}
        session.post(delete_url, data=delete_data)

        # Start download process
        wait_and_create_download_task(rd_id)

    else:
        console.log('❌ Failed to send to Real-Debrid:', r.text)

def wait_and_create_download_task(rd_id):
    console.log('⏳ Waiting for caching...')
    cached = False
    torrent_name = "unknown_torrent"

    for _ in range(40):  # 20 min max
        status_r = requests.get(
            f'https://api.real-debrid.com/rest/1.0/torrents/info/{rd_id}',
            headers={'Authorization': f'Bearer {RD_TOKEN}'}
        )
        if status_r.status_code == 200:
            status = status_r.json()
            torrent_name = status.get('filename', 'unknown_torrent').replace('/', '-').strip()

            if status['status'] == 'downloaded':
                cached = True
                console.log(f'✅ Torrent cached: {torrent_name}')

                # Create folder
                folder_path = os.path.join(SAVE_PATH, torrent_name)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                # Download each file inside the folder
                for link in status['links']:
                    filename = link.split('/')[-1].split('?')[0]
                    save_path = os.path.join(folder_path, filename)
                    task = DownloadTask(filename, link, save_path)
                    downloads.append(task)
                    task.start()
                break

        time.sleep(CHECK_INTERVAL)

    if not cached:
        console.log('❌ Torrent caching timeout.')

# Start Everything
if __name__ == "__main__":
    login_qbittorrent()

    threading.Thread(target=main_loop, daemon=True).start()

    sent_magnets = set()

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






























'''

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
CHECK_INTERVAL = 5  # seconds
DOWNLOAD_CHUNK_SIZE = 8192
# ====================

# Session for qBittorrent
session = requests.Session()
console = Console()
downloads = []  # List to hold active download tasks

class DownloadTask:
    def __init__(self, filename, url, save_path):
        self.filename = filename
        self.url = url
        self.save_path = save_path
        self.progress = 0
        self.status = "waiting"
        self.thread = threading.Thread(target=self.download)
        self._pause = threading.Event()
        self._pause.set()  # Start unpaused
        self._stop = threading.Event()

    def start(self):
        self.status = "downloading"
        self.thread.start()

    def download(self):
        try:
            # FIRST, unrestrict the Real-Debrid link
            unrestrict_r = requests.post(
                'https://api.real-debrid.com/rest/1.0/unrestrict/link',
                headers={'Authorization': f'Bearer ' + RD_TOKEN},
                data={'link': self.url}
            )
            if unrestrict_r.status_code == 200:
                unrestricted_url = unrestrict_r.json()['download']
                console.log(f'✅ Unrestricted URL for {self.filename}')
            else:
                console.log(f'❌ Failed to unrestrict {self.filename}: {unrestrict_r.text}')
                self.status = "error"
                return
            
            # THEN download from unrestricted URL
            r = requests.get(unrestricted_url, stream=True)
            total_length = int(r.headers.get('content-length', 0))
            if total_length == 0:
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

def make_table():
    table = Table(title="Real-Debrid Downloads")
    table.add_column("ID", style="cyan")
    table.add_column("Filename", style="magenta")
    table.add_column("Progress", style="green")
    table.add_column("Status", style="yellow")
    for i, task in enumerate(downloads):
        percent = (task.progress / os.path.getsize(task.save_path)) * 100 if os.path.exists(task.save_path) and os.path.getsize(task.save_path) > 0 else 0
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
            console.log(f"⚠️ Error: {e}")

def login_qbittorrent():
    r = session.post(QBIT_HOST + '/api/v2/auth/login', data={'username': QBIT_USER, 'password': QBIT_PASS})
    if 'Ok.' not in r.text:
        console.log('❌ Failed to login to qBittorrent')
        exit()
    else:
        console.log('✅ Logged in to qBittorrent')

def get_torrents():
    r = session.get(QBIT_HOST + '/api/v2/torrents/info')
    return r.json()

def send_to_rd(magnet, torrent_hash):
    r = requests.post(
        'https://api.real-debrid.com/rest/1.0/torrents/addMagnet',
        headers={'Authorization': f'Bearer {RD_TOKEN}'},
        data={'magnet': magnet}
    )
    if r.status_code == 201:
        console.log('✅ Sent to Real-Debrid:', magnet)
        rd_id = r.json()['id']

        # Step 1: Auto-select all files
        select_url = f'https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{rd_id}'
        select_data = {'files': 'all'}
        select_r = requests.post(select_url, headers={'Authorization': f'Bearer {RD_TOKEN}'}, data=select_data)
        if select_r.status_code == 204:
            console.log('✅ Selected all files automatically')
        else:
            console.log('⚠️ Failed to select files:', select_r.text)

        # Step 2: Delete torrent from qBittorrent
        delete_url = f"{QBIT_HOST}/api/v2/torrents/delete"
        delete_data = {'hashes': torrent_hash, 'deleteFiles': True}
        del_r = session.post(delete_url, data=delete_data)
        if del_r.status_code == 200:
            console.log('🗑️ Deleted from qBittorrent:', torrent_hash)
        else:
            console.log('⚠️ Failed to delete from qBittorrent:', del_r.text)

        # Step 3: Wait and Download
        wait_and_create_download_task(rd_id)

    else:
        console.log('❌ Failed to send to Real-Debrid:', r.text)

def wait_and_create_download_task(rd_id):
    console.log('⏳ Waiting for caching...')
    cached = False
    for _ in range(40):  # 20 min max
        status_r = requests.get(f'https://api.real-debrid.com/rest/1.0/torrents/info/{rd_id}',
                                headers={'Authorization': f'Bearer {RD_TOKEN}'})
        if status_r.status_code == 200:
            status = status_r.json()
            if status['status'] == 'downloaded':
                cached = True
                console.log('✅ Torrent is cached!')
                for link in status['links']:
                    filename = link.split('/')[-1].split('?')[0]
                    save_path = os.path.join(SAVE_PATH, filename)
                    task = DownloadTask(filename, link, save_path)
                    downloads.append(task)
                    task.start()
                break
        time.sleep(CHECK_INTERVAL)

    if not cached:
        console.log('❌ Torrent caching timeout.')

# Start Everything
if __name__ == "__main__":
    login_qbittorrent()

    # Start Terminal UI in parallel
    threading.Thread(target=main_loop, daemon=True).start()
    threading.Thread(target=user_controls, daemon=True).start()

    sent_magnets = set()

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
'''
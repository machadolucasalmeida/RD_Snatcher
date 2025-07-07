import requests
import time
import os

# === CONFIG HERE ===
RD_TOKEN = 'TI7IARLHWX7SD37EAVNVOBQ4QRA46XGXRVLXRTAWI223RWVYFOMA'
QBIT_HOST = 'http://localhost:8080'
QBIT_USER = 'machadolucas'
QBIT_PASS = 'Machado@Lucas157525#@$'
SAVE_PATH = r'C:\media\Downloads'  # Use r'' for Windows paths
CHECK_INTERVAL = 30  # seconds
DOWNLOAD_CHUNK_SIZE = 8192  # for streaming big files
# ====================

session = requests.Session()

def login_qbittorrent():
    r = session.post(QBIT_HOST + '/api/v2/auth/login', data={'username': QBIT_USER, 'password': QBIT_PASS})
    if 'Ok.' not in r.text:
        print('❌ Failed to login to qBittorrent')
        exit()
    else:
        print('✅ Logged in to qBittorrent')

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
        print('✅ Sent to Real-Debrid:', magnet)
        rd_id = r.json()['id']

        # Step 1: Auto-select all files
        select_url = f'https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{rd_id}'
        select_data = {'files': 'all'}
        select_r = requests.post(select_url, headers={'Authorization': f'Bearer {RD_TOKEN}'}, data=select_data)
        if select_r.status_code == 204:
            print('✅ Selected all files automatically')
        else:
            print('⚠️ Failed to select files:', select_r.text)

        # Step 2: Delete torrent from qBittorrent
        delete_url = f"{QBIT_HOST}/api/v2/torrents/delete"
        delete_data = {'hashes': torrent_hash, 'deleteFiles': True}
        del_r = session.post(delete_url, data=delete_data)
        if del_r.status_code == 200:
            print('🗑️ Deleted from qBittorrent:', torrent_hash)
        else:
            print('⚠️ Failed to delete from qBittorrent:', del_r.text)

        # Step 3: Wait for caching and download
        wait_and_download(rd_id)

    else:
        print('❌ Failed to send to Real-Debrid:', r.text)

def wait_and_download(rd_id):
    print('⏳ Waiting for caching...')
    cached = False
    for _ in range(40):  # Wait up to 40 * 30s = 20 minutes
        status_r = requests.get(f'https://api.real-debrid.com/rest/1.0/torrents/info/{rd_id}',
                                headers={'Authorization': f'Bearer {RD_TOKEN}'})
        if status_r.status_code == 200:
            status = status_r.json()
            if status['status'] == 'downloaded':
                cached = True
                print('✅ Torrent is cached!')
                download_files(status['links'])
                break
        time.sleep(CHECK_INTERVAL)

    if not cached:
        print('❌ Torrent caching timeout.')

def download_files(links):
    for link in links:
        filename = link.split('/')[-1].split('?')[0]
        save_path = os.path.join(SAVE_PATH, filename)

        print(f'⬇️ Downloading: {filename}')
        r = requests.get(link, stream=True)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
            print('✅ Downloaded:', filename)
        else:
            print('❌ Failed to download:', link)

# Start
login_qbittorrent()

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

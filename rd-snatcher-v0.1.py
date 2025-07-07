import requests
import time

# === CONFIG HERE ===
RD_TOKEN = 'TI7IARLHWX7SD37EAVNVOBQ4QRA46XGXRVLXRTAWI223RWVYFOMA'
QBIT_HOST = 'http://localhost:8080'
QBIT_USER = 'machadolucas'
QBIT_PASS = 'Machado@Lucas157525#@$'
SAVE_PATH = 'C:\\media\\Downloads'  # Notice double backslashes for Windows paths
CHECK_INTERVAL = 30  # seconds
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

        # Delete torrent and files from qBittorrent
        delete_url = f"{QBIT_HOST}/api/v2/torrents/delete"
        delete_data = {
            'hashes': torrent_hash,
            'deleteFiles': True  # Deletes torrent AND files
        }
        del_r = session.post(delete_url, data=delete_data)
        if del_r.status_code == 200:
            print('🗑️ Deleted from qBittorrent:', torrent_hash)
        else:
            print('⚠️ Failed to delete from qBittorrent:', del_r.text)

    else:
        print('❌ Failed to send to Real-Debrid:', r.text)

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

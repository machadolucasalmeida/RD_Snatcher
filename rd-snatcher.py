import requests
import time

# === CONFIG HERE ===
RD_TOKEN = 'TI7IARLHWX7SD37EAVNVOBQ4QRA46XGXRVLXRTAWI223RWVYFOMA'
QBIT_HOST = 'http://localhost:8080'
QBIT_USER = 'machadolucas'
QBIT_PASS = 'Machado@Lucas157525#@$'
SAVE_PATH = 'C:\media\Downloads'
CHECK_INTERVAL = 30  # seconds
# ====================

session = requests.Session()

def login_qbittorrent():
    r = session.post(QBIT_HOST + '/api/v2/auth/login', data={'username': QBIT_USER, 'password': QBIT_PASS})
    if 'Ok.' not in r.text:
        print('Failed to login to qBittorrent')
        exit()

def get_torrents():
    r = session.get(QBIT_HOST + '/api/v2/torrents/info')
    return r.json()

def send_to_rd(magnet):
    r = requests.post('https://api.real-debrid.com/rest/1.0/torrents/addMagnet', 
                      headers={'Authorization': f'Bearer {RD_TOKEN}'},
                      data={'magnet': magnet})
    if r.status_code == 201:
        print('Sent to Real-Debrid:', magnet)
    else:
        print('Failed to send:', r.text)

login_qbittorrent()

sent_magnets = set()

while True:
    torrents = get_torrents()
    for torrent in torrents:
        if torrent['state'] in ('metaDL', 'stalledDL', 'downloading'):
            hash_ = torrent['hash']
            magnet = f'magnet:?xt=urn:btih:{hash_}'
            if magnet not in sent_magnets:
                send_to_rd(magnet)
                sent_magnets.add(magnet)
    time.sleep(CHECK_INTERVAL)

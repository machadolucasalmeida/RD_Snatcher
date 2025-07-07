from rich.console import Console
from rich.live import Live
from rich.table import Table
import threading
import time
import requests
import os

console = Console()

downloads = []

class DownloadTask:
    def __init__(self, filename, url, save_path):
        self.filename = filename
        self.url = url
        self.save_path = save_path
        self.progress = 0
        self.status = "downloading"
        self.thread = threading.Thread(target=self.download)
        self._pause = threading.Event()
        self._pause.set()  # Start as unpaused
        self._stop = threading.Event()

    def start(self):
        self.thread.start()

    def download(self):
        r = requests.get(self.url, stream=True)
        total_length = int(r.headers.get('content-length', 0))
        with open(self.save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if self._stop.is_set():
                    console.log(f"Stopped {self.filename}")
                    return
                while not self._pause.is_set():
                    time.sleep(0.1)
                if chunk:
                    f.write(chunk)
                    self.progress += len(chunk)
        self.status = "finished"

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
        percent = (task.progress / os.path.getsize(task.save_path)) * 100 if os.path.exists(task.save_path) else 0
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
    # Example starting downloads (you would plug it into your RD downloader later)
    downloads.append(DownloadTask("Movie1.mkv", "https://some-link.com/file1", r"C:\media\Downloads\Movie1.mkv"))
    downloads.append(DownloadTask("Movie2.mkv", "https://some-link.com/file2", r"C:\media\Downloads\Movie2.mkv"))
    
    for task in downloads:
        task.start()

    threading.Thread(target=main_loop, daemon=True).start()
    user_controls()

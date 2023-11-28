import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from threading import Thread
import requests
import os
import hashlib
import time
from threading import Lock
import logging
from urllib.parse import urlparse, unquote

# Setup logging to file
logging.basicConfig(filename='download_errors.log', level=logging.ERROR)

# Global variables for progress tracking
progress_lock = Lock()
downloaded_bytes = 0

def log_error(error_message):
    """Log an error message to a file."""
    logging.error(error_message)

def get_checksum(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def update_progress_label(progress_label, text):
    progress_label['text'] = text

def update_progress_bar(progress_bar, value):
    progress_bar['value'] = value

def download_chunk(url, start, end, save_path, total_size, retry_count=0):
    global downloaded_bytes, progress_lock
    try:
        headers = {'Range': f'bytes={start}-{end}'}
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        with open(save_path, 'r+b') as f:
            f.seek(start)
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    with progress_lock:
                        downloaded_bytes += len(chunk)
                        progress = (downloaded_bytes / total_size) * 100
                        window.after_idle(lambda: update_progress_bar(progress_bar, progress))
                        window.after_idle(lambda: update_progress_label(progress_label, f"Download Progress: {progress:.2f}%"))
    except requests.RequestException as e:
        if retry_count < 3:
            time.sleep(5)  # Wait for 5 seconds before retrying
            download_chunk(url, start, end, save_path, total_size, retry_count + 1)
        else:
            log_error(f"Chunk {start}-{end} failed after {retry_count} retries: {e}")

def download_file(url, save_path, progress_bar, progress_label, window):
    global downloaded_bytes
    downloaded_bytes = 0  # Reset the downloaded bytes for each new download
    response = requests.head(url)
    total_size = int(response.headers.get('content-length', 0))
    if os.path.exists(save_path):
        current_size = os.path.getsize(save_path)
        if current_size < total_size:
            start_from = current_size
        else:
            if get_checksum(save_path) != response.headers.get('Content-MD5'):
                start_from = 0
            else:
                messagebox.showinfo("Info", "File already downloaded and verified.")
                return
    else:
        start_from = 0
        with open(save_path, 'wb') as f:
            f.truncate(total_size)

    chunk_size = 1024 * 1024
    num_chunks = (total_size - start_from) // chunk_size

    threads = []
    for i in range(num_chunks + 1):
        start = start_from + i * chunk_size
        end = start + chunk_size - 1
        if end >= total_size:
            end = total_size - 1
        thread = Thread(target=download_chunk, args=(url, start, end, save_path, total_size))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    window.after_idle(lambda: update_progress_label(progress_label, "Download Complete"))
    window.after_idle(lambda: update_progress_bar(progress_bar, 100))

def select_save_path():
    save_path = filedialog.askdirectory()
    if save_path:
        save_path_entry.delete(0, tk.END)
        save_path_entry.insert(tk.END, save_path)

def start_download_threaded():
    url = url_entry.get()
    directory = save_path_entry.get()
    parsed_url = urlparse(url)
    filename = os.path.basename(unquote(parsed_url.path))
    if not filename:
        messagebox.showerror("Error", "Could not extract filename from URL.")
        return
    save_path = os.path.join(directory, filename)
    Thread(target=download_file, args=(url, save_path, progress_bar, progress_label, window)).start()

window = tk.Tk()
window.title("Saim fast python Downloader")
window.geometry("500x300")

style = ttk.Style()
style.theme_use('clam')

url_label = ttk.Label(window, text="URL:")
url_label.pack(pady=10)

url_entry = ttk.Entry(window, width=50)
url_entry.pack()

save_path_label = ttk.Label(window, text="Save Path:")
save_path_label.pack(pady=10)

save_path_entry = ttk.Entry(window, width=50)
save_path_entry.pack()
select_path_button = ttk.Button(window, text="Select", command=select_save_path)
select_path_button.pack(pady=5)
download_button = ttk.Button(window, text="Start Download", command=start_download_threaded)
download_button.pack(pady=5)
progress_label = ttk.Label(window, text="Download Progress: 0.00%")
progress_label.pack(pady=10)
progress_bar = ttk.Progressbar(window, length=200, mode='determinate')
progress_bar.pack()
window.mainloop()

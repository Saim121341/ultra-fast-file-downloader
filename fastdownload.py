import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from threading import Thread
import requests
import os
import hashlib
import time
from threading import Lock
import logging
from urllib.parse import parse_qs, urlparse
import base64
from requests_html import HTMLSession
from urllib.parse import urlparse

# Setup logging to file
logging.basicConfig(filename='download_errors.log', level=logging.ERROR)

class Downloader:
    def __init__(self):
        self.progress_lock = Lock()
        self.downloaded_bytes = 0

    def log_error(self, error_message):
        """Log an error message to a file."""
        logging.error(error_message)

    def get_checksum(self, file_path):
        """Calculate MD5 checksum for a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def resolve_url(self, url):
        """Resolve complex redirections including decoding base64 URLs."""
        session = HTMLSession()
        try:
            # Check if the URL contains base64 encoded part
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            if 'url' in query_params:
                encoded_url = query_params['url'][0]
                decoded_url = base64.b64decode(encoded_url).decode('utf-8')
                response = session.get(decoded_url)
            else:
                response = session.get(url)

            response.html.render()
            final_url = response.url
        except Exception as e:
            self.log_error(f"Error resolving URL: {e}")
            final_url = url  # Fallback to the original URL in case of an error
        finally:
            session.close()
        return final_url

    def download_chunk(self, url, start, end, save_path, total_size, progress_bar, progress_label, window, retry_count=0):
        """Download a chunk of the file."""
        try:
            headers = {'Range': f'bytes={start}-{end}'}
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            with open(save_path, 'r+b') as f:
                f.seek(start)
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
                        with self.progress_lock:
                            self.downloaded_bytes += len(chunk)
                            progress = (self.downloaded_bytes / total_size) * 100
                            window.after_idle(lambda: self.update_progress_bar(progress_bar, progress))
                            window.after_idle(lambda: self.update_progress_label(progress_label, f"Download Progress: {progress:.2f}%"))
        except requests.RequestException as e:
            if retry_count < 3:
                time.sleep(5)  # Wait for 5 seconds before retrying
                self.download_chunk(url, start, end, save_path, total_size, progress_bar, progress_label, window, retry_count + 1)
            else:
                self.log_error(f"Chunk {start}-{end} failed after {retry_count} retries: {e}")

    def update_progress_label(self, progress_label, text):
        """Update the progress label in the GUI."""
        progress_label['text'] = text

    def update_progress_bar(self, progress_bar, value):
        """Update the progress bar in the GUI."""
        progress_bar['value'] = value

    def download_file(self, url, save_path, progress_bar, progress_label, window):
        """Download a file with progress tracking."""
        self.downloaded_bytes = 0  # Reset the downloaded bytes for each new download

        # Resolve complex redirections
        final_url = self.resolve_url(url)

        response = requests.head(final_url)
        total_size = int(response.headers.get('content-length', 0))

        if os.path.exists(save_path):
            current_size = os.path.getsize(save_path)
            if current_size < total_size:
                start_from = current_size
            else:
                if self.get_checksum(save_path) != response.headers.get('Content-MD5'):
                    start_from = 0
                else:
                    messagebox.showinfo("Info", "File already downloaded and verified.")
                    return
        else:
            start_from = 0
            with open(save_path, 'wb') as f:
                f.truncate(total_size)

        chunk_size = 1024 * 1024  # 1 MB
        num_chunks = (total_size - start_from) // chunk_size

        threads = []
        for i in range(num_chunks + 1):
            start = start_from + i * chunk_size
            end = start + chunk_size - 1
            if end >= total_size:
                end = total_size - 1
            thread = Thread(target=self.download_chunk, args=(final_url, start, end, save_path, total_size, progress_bar, progress_label, window))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        window.after_idle(lambda: self.update_progress_label(progress_label, "Download Complete"))
        window.after_idle(lambda: self.update_progress_bar(progress_bar, 100))

# GUI Setup
class DownloadApp:
    def __init__(self, window, downloader):
        self.window = window
        self.downloader = downloader
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI elements for the downloader."""
        self.url_label = ttk.Label(self.window, text="URL:")
        self.url_label.pack(pady=10)

        self.url_entry = ttk.Entry(self.window, width=50)
        self.url_entry.pack()

        self.save_path_label = ttk.Label(self.window, text="Save Path:")
        self.save_path_label.pack(pady=10)

        self.save_path_entry = ttk.Entry(self.window, width=50)
        self.save_path_entry.pack()

        self.select_path_button = ttk.Button(self.window, text="Select", command=self.select_save_path)
        self.select_path_button.pack(pady=5)

        self.download_button = ttk.Button(self.window, text="Start Download", command=self.start_download_threaded)
        self.download_button.pack(pady=5)

        self.progress_label = ttk.Label(self.window, text="Download Progress: 0.00%")
        self.progress_label.pack(pady=10)

        self.progress_bar = ttk.Progressbar(self.window, length=200, mode='determinate')
        self.progress_bar.pack()

    def select_save_path(self):
        """Open a dialog to select the save path."""
        save_path = filedialog.askdirectory()
        if save_path:
            self.save_path_entry.delete(0, tk.END)
            self.save_path_entry.insert(tk.END, save_path)

    def start_download_threaded(self):
        """Start the download in a separate thread."""
        url = self.url_entry.get()
        directory = self.save_path_entry.get()

        # Extract a valid file name from the URL or use a predefined name
        filename = "downloaded_file"  # Default file name
        try:
            parsed_url = urlparse(url)
            if parsed_url.path:
                filename = os.path.basename(parsed_url.path)
                # Replace invalid characters in filename
                filename = filename.replace(":", "_").replace("?", "_").replace("/", "_")
            if not filename:
                raise ValueError("No valid filename found in URL")
        except Exception as e:
            messagebox.showerror("Error", f"Error processing file name: {e}")
            return

        save_path = os.path.join(directory, filename)
        Thread(target=self.downloader.download_file, args=(url, save_path, self.progress_bar, self.progress_label, self.window)).start()

# Main Application
if __name__ == "__main__":
    window = tk.Tk()
    window.title("Saim Fast Python Downloader")
    window.geometry("500x300")

    downloader = Downloader()
    app = DownloadApp(window, downloader)
    window.mainloop()

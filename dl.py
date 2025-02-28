import os
import re
import time
import urllib3
import requests
import threading
from urllib.parse import unquote
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SmartDownloader:
    def __init__(self):
        self.base_dir = os.path.join(os.getcwd(), "downloads")
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.max_retry = 3
        self.init_concurrency = 6
        self.lock = threading.Lock()

    def _create_version_dir(self):
        """创建带版本号的目录"""
        existing = [d for d in os.listdir(self.base_dir) if d.startswith(self.today)]
        release_num = len(existing) + 1
        self.download_dir = os.path.join(self.base_dir, f"{self.today}-{release_num}")
        os.makedirs(self.download_dir, exist_ok=True)

    def _parse_url(self, url):
        """智能解析URL参数"""
        path_match = re.search(r'path=([^&]*)', url)
        file_match = re.search(r'fileName=([^&]*)', url)
        
        raw_path = unquote(path_match.group(1)).strip("/") if path_match else ""
        filename = unquote(file_match.group(1)) if file_match else ""
        filename = os.path.basename(filename) if filename else os.path.basename(url.split("/")[-1].split("?")[0])

        if raw_path:
            path_parts = raw_path.split('/')
            # 当路径末段与文件名相同时，识别为重复路径段
            if path_parts and path_parts[-1] == filename:
                corrected_path = '/'.join(path_parts[:-1])
            else:
                corrected_path = raw_path
            full_dir = os.path.join(self.download_dir, corrected_path)
        else:
            full_dir = self.download_dir

        os.makedirs(full_dir, exist_ok=True)
        return full_dir, filename

    def _download_file(self, url):
        """下载核心逻辑"""
        full_dir, filename = self._parse_url(url)
        file_path = os.path.join(full_dir, filename)
        temp_file = f"{file_path}.part"
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        for retry in range(self.max_retry + 1):
            try:
                with requests.get(
                    url,
                    stream=True,
                    timeout=30,
                    verify=False,
                    proxies={"http": None, "https": None}
                ) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))

                    with open(temp_file, 'wb') as f, tqdm(
                        desc=filename[:20],
                        total=total_size,
                        unit='iB',
                        unit_scale=True,
                        leave=False,
                        mininterval=0.3,
                        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]"
                    ) as bar:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                bar.update(len(chunk))

                os.replace(temp_file, file_path)
                return True

            except Exception as e:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                if retry == self.max_retry:
                    return False
                time.sleep(2 ** retry)
        return False

    def start(self):
        """启动下载"""
        if not os.path.exists('urls.txt'):
            print("错误：未找到urls.txt文件")
            return

        with open('urls.txt', 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
        
        self._create_version_dir()
        
        succeeded_urls = set()
        remaining_urls = urls.copy()
        total = len(urls)
        
        with tqdm(total=total, desc="总进度", position=0, unit="文件") as pbar:
            while remaining_urls:
                current_batch = remaining_urls
                remaining_urls = []
                failed_in_batch = []
                
                with ThreadPoolExecutor(max_workers=self.init_concurrency) as executor:
                    futures = {executor.submit(self._download_file, url): url for url in current_batch}
                    for future in as_completed(futures):
                        url = futures[future]
                        success = False
                        try:
                            success = future.result()
                        except:
                            pass
                        if success:
                            with self.lock:
                                if url not in succeeded_urls:
                                    succeeded_urls.add(url)
                                    pbar.update(1)
                        else:
                            failed_in_batch.append(url)
                
                remaining_urls = failed_in_batch.copy()

        print(f"\n下载完成！文件保存在：{self.download_dir}")

if __name__ == "__main__":
    downloader = SmartDownloader()
    downloader.start()

#!/usr/bin/env python3
"""
Snapchat Memories Downloader
Downloads all memories from a Snapchat export HTML file with reliability features.
"""

import os
import sys
import json
import time
import re
import argparse
import zipfile
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


class SnapchatMemoriesDownloader:
    def __init__(self, html_file, output_dir="downloads", delay=1.0, max_retries=3, workers=1):
        self.html_file = html_file
        self.output_dir = Path(output_dir)
        self.delay = delay
        self.max_retries = max_retries
        self.workers = workers
        
        # Thread safety
        self.state_lock = Lock()
        self.stats_lock = Lock()
        
        # Create output directories
        self.images_dir = self.output_dir / "images"
        self.videos_dir = self.output_dir / "videos"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        
        # State tracking
        self.state_file = self.output_dir / "download_state.json"
        self.failed_log = self.output_dir / "failed_downloads.log"
        self.downloaded_files = self.load_state()
        
        # Statistics
        self.stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0
        }
        
        # HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        })

    def load_state(self):
        """Load previously downloaded files from state file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load state file: {e}")
                return {}
        return {}

    def save_state(self):
        """Save current download state (thread-safe)."""
        with self.state_lock:
            try:
                with open(self.state_file, 'w') as f:
                    json.dump(self.downloaded_files, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not save state file: {e}")

    def log_failure(self, url, error):
        """Log failed download to file."""
        with open(self.failed_log, 'a') as f:
            timestamp = datetime.now().isoformat()
            f.write(f"[{timestamp}] {url}\n")
            f.write(f"Error: {error}\n\n")

    def extract_sid_from_url(self, url):
        """Extract the session ID (sid) from URL for unique identification."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            return params.get('sid', [None])[0]
        except Exception:
            return None

    def parse_html(self):
        """Parse HTML file and extract download links with metadata."""
        print(f"Parsing {self.html_file}...")
        
        with open(self.html_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # Find all table rows with download links
        memories = []
        rows = soup.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 4:
                date_cell = cells[0].get_text(strip=True)
                media_type = cells[1].get_text(strip=True)
                
                # Find download link
                link = cells[3].find('a', onclick=True)
                if link:
                    onclick = link.get('onclick', '')
                    # Extract URL from onclick="downloadMemories('URL', this, true/false)"
                    match = re.search(r"downloadMemories\('(.+?)',\s*this,\s*(true|false)\)", onclick)
                    if match:
                        url = match.group(1)
                        is_get_request = match.group(2) == 'true'
                        
                        memories.append({
                            'url': url,
                            'date': date_cell,
                            'media_type': media_type,
                            'is_get_request': is_get_request
                        })
        
        print(f"Found {len(memories)} memories to download")
        return memories

    def generate_filename(self, memory):
        """Generate filename based on date and unique ID."""
        # Parse date
        try:
            date_str = memory['date'].replace(' UTC', '')
            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            date_part = dt.strftime('%Y-%m-%d_%H-%M-%S')
        except Exception:
            date_part = 'unknown_date'
        
        # Get unique ID
        sid = self.extract_sid_from_url(memory['url'])
        if sid:
            unique_part = sid[:16]  # first 16 chars of sid
        else:
            unique_part = str(hash(memory['url']))[:16]
        
        # Determine extension
        media_type = memory['media_type'].lower()
        if media_type == 'video':
            ext = 'mp4'
        elif media_type == 'image':
            ext = 'jpg'
        else:
            ext = 'bin'
        
        return f"{date_part}_{unique_part}.{ext}"

    def _extract_zip_if_needed(self, file_path):
        """Extract main file from ZIP archive if file is a ZIP (Snapchat overlays)."""
        try:
            if zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, 'r') as zf:
                    # Find the main file (ends with -main.jpg for images, -main.mp4 for videos)
                    main_file = None
                    for name in zf.namelist():
                        if name.endswith('-main.jpg') or name.endswith('-main.mp4'):
                            main_file = name
                            break
                    
                    if main_file:
                        # Extract to temporary location
                        temp_path = file_path.parent / f"temp_{file_path.name}"
                        with open(temp_path, 'wb') as f:
                            f.write(zf.read(main_file))
                        
                        # Replace ZIP with extracted file
                        file_path.unlink()
                        temp_path.rename(file_path)
        except Exception as e:
            # Log warning but don't fail the download
            print(f"\nWarning: Could not extract ZIP for {file_path.name}: {e}")

    def download_file(self, memory):
        """Download a single file with retry logic (thread-safe)."""
        url = memory['url']
        is_get_request = memory['is_get_request']
        
        # Check if already downloaded
        sid = self.extract_sid_from_url(url)
        if sid and sid in self.downloaded_files:
            with self.stats_lock:
                self.stats['skipped'] += 1
            return True
        
        # Generate filename and determine output directory
        filename = self.generate_filename(memory)
        if memory['media_type'].lower() == 'video':
            output_path = self.videos_dir / filename
        else:
            output_path = self.images_dir / filename
        
        # Check if file already exists on disk
        if output_path.exists() and output_path.stat().st_size > 0:
            if sid:
                self.downloaded_files[sid] = str(output_path)
                self.save_state()
            self.stats['skipped'] += 1
            return True
        
        # Retry loop
        for attempt in range(self.max_retries):
            try:
                if is_get_request:
                    # GET request with custom header
                    headers = self.session.headers.copy()
                    headers['X-Snap-Route-Tag'] = 'mem-dmd'
                    
                    response = self.session.get(url, headers=headers, timeout=60)
                    response.raise_for_status()
                    
                    # Save file
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                else:
                    # POST request (for proxy downloads)
                    parts = url.split('?', 1)
                    base_url = parts[0]
                    params = parts[1] if len(parts) > 1 else ''
                    
                    response = self.session.post(
                        base_url,
                        data=params,
                        headers={'Content-Type': 'application/x-www-form-urlencoded'},
                        timeout=60
                    )
                    response.raise_for_status()
                    
                    # The response should contain a download URL
                    download_url = response.text.strip()
                    
                    # Download from the returned URL
                    download_response = self.session.get(download_url, timeout=60)
                    download_response.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        f.write(download_response.content)
                
                # Verify file was downloaded
                if output_path.exists() and output_path.stat().st_size > 0:
                    # Extract from ZIP if needed (for Snapchat overlays)
                    self._extract_zip_if_needed(output_path)
                    
                    if sid:
                        with self.state_lock:
                            self.downloaded_files[sid] = str(output_path)
                        self.save_state()
                    with self.stats_lock:
                        self.stats['successful'] += 1
                    return True
                else:
                    raise Exception("Downloaded file is empty")
                    
            except Exception as e:
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                else:
                    # Final attempt failed
                    error_msg = f"Failed after {self.max_retries} attempts: {str(e)}"
                    self.log_failure(url, error_msg)
                    with self.stats_lock:
                        self.stats['failed'] += 1
                    return False
        
        return False

    def run(self):
        """Main execution function."""
        start_time = time.time()
        
        # Parse HTML
        memories = self.parse_html()
        self.stats['total'] = len(memories)
        
        if not memories:
            print("No memories found in HTML file!")
            return
        
        print(f"\nStarting download of {len(memories)} memories...")
        print(f"Output directory: {self.output_dir.absolute()}")
        print(f"Already downloaded: {len(self.downloaded_files)}")
        print(f"Workers: {self.workers} {'(parallel)' if self.workers > 1 else '(sequential)'}")
        print(f"Delay between downloads: {self.delay}s")
        print(f"Max retries per file: {self.max_retries}\n")
        
        if self.workers == 1:
            # Sequential download (original behavior)
            self._run_sequential(memories)
        else:
            # Parallel download
            self._run_parallel(memories)
        
        # Print summary
        duration = time.time() - start_time
        print("\n" + "="*60)
        print("DOWNLOAD COMPLETE")
        print("="*60)
        print(f"Total memories: {self.stats['total']}")
        print(f"Successfully downloaded: {self.stats['successful']}")
        print(f"Already existed (skipped): {self.stats['skipped']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"Duration: {duration:.1f} seconds")
        
        if self.workers > 1:
            rate = self.stats['total'] / duration if duration > 0 else 0
            print(f"Average rate: {rate:.1f} files/second")
        
        print(f"\nFiles saved to: {self.output_dir.absolute()}")
        
        if self.stats['failed'] > 0:
            print(f"Failed downloads logged to: {self.failed_log}")
        
        print("="*60)

    def _run_sequential(self, memories):
        """Run downloads sequentially (original behavior)."""
        with tqdm(total=len(memories), desc="Downloading", unit="file") as pbar:
            for i, memory in enumerate(memories):
                # Update progress bar with current file info
                pbar.set_postfix_str(f"{memory['media_type']} - {memory['date'][:10]}")
                
                # Download
                success = self.download_file(memory)
                
                # Update progress
                pbar.update(1)
                
                # Rate limiting (except for last file)
                if i < len(memories) - 1 and success:
                    time.sleep(self.delay)

    def _run_parallel(self, memories):
        """Run downloads in parallel using ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            # Create a progress bar
            with tqdm(total=len(memories), desc="Downloading", unit="file") as pbar:
                # Submit all download tasks
                future_to_memory = {
                    executor.submit(self._download_with_delay, memory): memory 
                    for memory in memories
                }
                
                # Process completed downloads
                for future in as_completed(future_to_memory):
                    memory = future_to_memory[future]
                    try:
                        success = future.result()
                        pbar.set_postfix_str(f"{memory['media_type']} - {memory['date'][:10]}")
                    except Exception as e:
                        print(f"\nError downloading {memory['date']}: {e}")
                    finally:
                        pbar.update(1)

    def _download_with_delay(self, memory):
        """Download a file and apply rate limiting."""
        success = self.download_file(memory)
        if success and self.delay > 0:
            time.sleep(self.delay)
        return success


def main():
    parser = argparse.ArgumentParser(
        description='Download all memories from Snapchat export HTML file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s html/memories_history.html
  %(prog)s html/memories_history.html -o my_memories -d 0.5
  %(prog)s html/memories_history.html --workers 5
  %(prog)s html/memories_history.html --workers 10 --delay 0.2
  %(prog)s html/memories_history.html --max-retries 5 --workers 20
        """
    )
    
    parser.add_argument(
        'html_file',
        help='Path to the memories_history.html file'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='downloads',
        help='Output directory for downloaded files (default: downloads)'
    )
    
    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=1.0,
        help='Delay between downloads in seconds (default: 1.0)'
    )
    
    parser.add_argument(
        '-r', '--max-retries',
        type=int,
        default=3,
        help='Maximum retry attempts per file (default: 3)'
    )
    
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=1,
        help='Number of concurrent download workers (default: 1, recommended: 5-10'
    )
    
    args = parser.parse_args()
    
    # Validate HTML file exists
    if not os.path.exists(args.html_file):
        print(f"Error: File not found: {args.html_file}")
        sys.exit(1)
    
    # Validate workers parameter
    if args.workers < 1:
        print("Error: --workers must be at least 1")
        sys.exit(1)
    if args.workers > 10:
        print("Warning: Using more than 10 workers may cause rate limiting or connection issues")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    # Create and run downloader
    downloader = SnapchatMemoriesDownloader(
        html_file=args.html_file,
        output_dir=args.output,
        delay=args.delay,
        max_retries=args.max_retries,
        workers=args.workers
    )
    
    try:
        downloader.run()
    except KeyboardInterrupt:
        print("\n\nDownload interrupted by user.")
        print("Progress has been saved. Run the script again to resume.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

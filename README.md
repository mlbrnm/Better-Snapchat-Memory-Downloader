# Snapchat Memories Downloader

A Python script for downloading all memories from your Snapchat data export. I made this after struggling with Snapchat's provided solution which is (intentionally?) terrible.

<img width="1142" height="169" alt="image" src="https://github.com/user-attachments/assets/318f14fc-6172-4fef-8993-46e148452984" />
<img width="1134" height="174" alt="image" src="https://github.com/user-attachments/assets/340d6758-4818-4613-a1bd-8e1654019de1" />


## Summary of Improvements Compared to Basic Snapchat Export

- Filenames of photos/videos are set based on their date so it is clear when each was taken.
- Sets metadata for photos/videos correctly so services like Google or Apple Photos know when they were taken and can sort/filter appropriately.
- Automatically extracts the base image/video from Snaps with overlays (text/stickers) instead of leaving it as a zip with no extension.
- Doesn't rely on browser download management which may block multiple file downloads.
- Checks that files have actually downloaded, and retries if they fail.
- Skips already downloaded files so you can stop it and resume, or only download new Snaps since your last export.
- Configurable number of parallel downloads, retries, delay between files.

## Features

**More Reliable Downloads**
- Automatic retry with exponential backoff (3 attempts per file by default)
- Verification of successful downloads (HTTP 200 + file size > 0)

**Progress Tracking**
- Progress bar with file count and percentage
- Shows current file being downloaded (type and date)
- Summary report at completion

**Resume Capability**
- Saves download state to JSON file
- Automatically skips already downloaded files
- Can be interrupted and resumed without losing progress

**Organized Storage**
- Images saved to `downloads/images/`
- Videos saved to `downloads/videos/`
- Files named with timestamp and unique ID: `YYYY-MM-DD_HH-MM-SS_{sid}.{ext}`

**Error Handling**
- Failed downloads logged to `downloads/failed_downloads.log`
- Continues on individual failures, doesn't crash
- Detailed error messages for troubleshooting

**Zip Extraction**
- Snaps with overlays are downloaded as zips (with no extension - thanks Snapchat).
- Automatically extracts the main image from the zip and discards the rest.
- (I may add the ability to optionally combine the overlays into a final image instead.)

## Requirements

- [Python 3](https://www.python.org/) - I am using 3.13.7 but I think any recent ish version should be fine
- [Exiftool](https://exiftool.org/) installed and accessible in path (if you open a CMD/terminal and enter `exiftool` it shouldn't say it doesn't exist)


## Setup

1. Export your Snapchat memories from the Snapchat desktop website.
2. Place the files from this repo (the two .py files and requirements.txt) in the root folder (MYDATA~xxxxxx).
<img width="628" height="170" alt="Screenshot 2025-11-11 at 10 34 28 PM" src="https://github.com/user-attachments/assets/8c60d2eb-b3ca-44ed-b216-772b5ccb9676" />

3. Install required Python packages.

```bash
pip3 install -r requirements.txt
```

## Basic Usage (Sequential)
To download all memories:
```bash
python3 download_snapchat_memories.py html/memories_history.html
```

To set metadata dates of photos and videos:
```bash
python3 set_snapchat_metadata.py downloads/
```

### Parallel Download and Customization (Recommended)
```bash
# Conservative parallel (5 workers and 0.5 second delay - worked for me and was fast enough I didn't bother going further)
python3 download_snapchat_memories.py html/memories_history.html --workers 5 --delay 0.5
```

### Custom Output Directory
```bash
python3 download_snapchat_memories.py html/memories_history.html -o my_memories
```

### Increase Retry Attempts
```bash
python3 download_snapchat_memories.py html/memories_history.html --max-retries 5
```

### All Options Combined
```bash
python3 download_snapchat_memories.py html/memories_history.html \
  --output my_snapchat_memories \
  --workers 5 \
  --delay 0.2 \
  --max-retries 5
```

To set metadata dates of photos and videos:
```bash
python3 set_snapchat_metadata.py downloads/
```

## Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `html_file` | - | Required | Path to the memories_history.html file |
| `--output` | `-o` | `downloads` | Output directory for downloaded files |
| `--delay` | `-d` | `1.0` | Delay between downloads in seconds |
| `--max-retries` | `-r` | `3` | Maximum retry attempts per file |
| `--workers` | `-w` | `1` | Number of concurrent download workers (1=sequential, 5=recommended) |

## Output Structure

```
downloads/
├── images/
│   ├── 2025-11-10_14-44-41_{unique-id}.jpg
│   ├── 2025-11-09_20-58-43_{unique-id}.jpg
│   └── ...
├── videos/
│   ├── 2025-11-07_14-32-49_{unique-id}.mp4
│   ├── 2025-10-27_00-08-03_{unique-id}.mp4
│   └── ...
├── download_state.json (tracks progress)
└── failed_downloads.log (if any failures occur)
```

## Resume After Interruption

If the download is interrupted (Ctrl+C, network issue, etc.), run the same command again:

```bash
python3 download_snapchat_memories.py html/memories_history.html
```

etc

The script will:
1. Load the previous download state from `download_state.json`
2. Skip files that were already downloaded
3. Continue from where it left off

## Important Notes

**Download Links Expire**: When you trigger the export from Snapchat, you must download your export archive within 3 days. And then you must download all the files from that export archive within 7 days.

**Snaps with Overlays**: Currently, the overlays are discarded and only the base image/video is retained. I may look into merging the overlays onto the base image in the future but I made this for personal/family use and that wasn't a priority.

## Troubleshooting

### "No memories found" Error
- Verify you're pointing to the correct HTML file
- Ensure the HTML file contains the memories table

### Script Crashes
- Check that all dependencies are installed: `pip3 install -r requirements.txt`
- Review the error message for specific issues
- Check `downloads/failed_downloads.log` for details

## Dependencies

- `requests>=2.31.0` - HTTP library for downloads
- `beautifulsoup4>=4.12.0` - HTML parsing
- `tqdm>=4.66.0` - Progress bar display
- `piexif>=1.1.3` - Adding date metadata to images
- (exiftool - installed separately)

## License

This script is provided as-is for personal use in downloading your own Snapchat data export. Feel free to do whatever you want with it. I made it for personal/family use and thought others might be interested as Snapchat's provided solution is bad.

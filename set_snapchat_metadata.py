#!/usr/bin/env python3
"""
Snapchat Metadata Setter
Sets EXIF metadata on downloaded Snapchat memories based on filenames.
"""

import os
import sys
import re
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import piexif


class SnapchatMetadataSetter:
    def __init__(self, directory, force=False):
        self.directory = Path(directory)
        self.force = force
        
        # Statistics
        self.stats = {
            'total': 0,
            'processed': 0,
            'skipped': 0,
            'failed': 0
        }
    
    def parse_date_from_filename(self, filename):
        """Extract datetime from filename format: YYYY-MM-DD_HH-MM-SS_*.ext"""
        # Match pattern: YYYY-MM-DD_HH-MM-SS
        match = re.match(r'(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})', filename)
        if match:
            year, month, day, hour, minute, second = match.groups()
            try:
                return datetime(int(year), int(month), int(day), 
                              int(hour), int(minute), int(second))
            except ValueError:
                return None
        return None
    
    def has_exif_date(self, file_path):
        """Check if image already has EXIF date metadata."""
        if self.force:
            return False
        
        try:
            exif_dict = piexif.load(str(file_path))
            # Check if DateTimeOriginal exists
            if piexif.ExifIFD.DateTimeOriginal in exif_dict.get('Exif', {}):
                return True
        except:
            pass
        return False
    
    def set_image_metadata(self, file_path, dt):
        """Set EXIF metadata for image files using piexif."""
        # Check if already has metadata (unless force is enabled)
        if self.has_exif_date(file_path):
            return 'skipped'
        
        # Format datetime for EXIF (YYYY:MM:DD HH:MM:SS)
        exif_datetime = dt.strftime('%Y:%m:%d %H:%M:%S')
        
        try:
            # Load existing EXIF data or create new
            try:
                exif_dict = piexif.load(str(file_path))
            except:
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
            
            # Set datetime tags in Exif IFD
            exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = exif_datetime.encode()
            exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = exif_datetime.encode()
            
            # Set datetime in 0th IFD (main image)
            exif_dict['0th'][piexif.ImageIFD.DateTime] = exif_datetime.encode()
            
            # Convert to bytes and save
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, str(file_path))
            
            return 'success'
        except Exception as e:
            raise Exception(f"Failed to set image EXIF data: {e}")
    
    def set_video_metadata(self, file_path, dt):
        """Set metadata for video files using exiftool."""
        # Format datetime for exiftool
        exif_datetime = dt.strftime('%Y:%m:%d %H:%M:%S')
        
        try:
            # Use exiftool to set video metadata
            # -overwrite_original prevents creating backup files
            result = subprocess.run([
                'exiftool',
                '-overwrite_original',
                f'-CreateDate={exif_datetime}',
                f'-ModifyDate={exif_datetime}',
                f'-MediaCreateDate={exif_datetime}',
                f'-MediaModifyDate={exif_datetime}',
                f'-TrackCreateDate={exif_datetime}',
                f'-TrackModifyDate={exif_datetime}',
                str(file_path)
            ], check=True, capture_output=True, text=True)
            
            return 'success'
        except subprocess.CalledProcessError as e:
            raise Exception(f"exiftool failed: {e.stderr}")
        except FileNotFoundError:
            raise Exception("exiftool not found - please install it and make sure it is in path (required for videos)")
    
    def process_file(self, file_path):
        """Process a single file."""
        # Parse date from filename
        dt = self.parse_date_from_filename(file_path.name)
        if not dt:
            return 'skipped', f"Could not parse date from filename: {file_path.name}"
        
        # Determine file type
        extension = file_path.suffix.lower()
        
        try:
            if extension in ['.jpg', '.jpeg']:
                result = self.set_image_metadata(file_path, dt)
                return result, None
            elif extension in ['.mp4', '.mov']:
                result = self.set_video_metadata(file_path, dt)
                return result, None
            else:
                return 'skipped', f"Unsupported file type: {extension}"
        except Exception as e:
            return 'failed', str(e)
    
    def find_media_files(self):
        """Find all image and video files in the directory."""
        media_files = []
        
        # Look for images
        images_dir = self.directory / "images"
        if images_dir.exists():
            for ext in ['*.jpg', '*.jpeg']:
                media_files.extend(images_dir.glob(ext))
        
        # Look for videos
        videos_dir = self.directory / "videos"
        if videos_dir.exists():
            for ext in ['*.mp4', '*.mov']:
                media_files.extend(videos_dir.glob(ext))
        
        # If no subdirectories, search in main directory
        if not media_files:
            for ext in ['*.jpg', '*.jpeg', '*.mp4', '*.mov']:
                media_files.extend(self.directory.glob(ext))
        
        return sorted(media_files)
    
    def run(self):
        """Main execution function."""
        print(f"Scanning directory: {self.directory.absolute()}")
        
        # Find all media files
        media_files = self.find_media_files()
        self.stats['total'] = len(media_files)
        
        if not media_files:
            print("No media files found!")
            return
        
        print(f"Found {len(media_files)} media files")
        if self.force:
            print("Force mode: Will overwrite existing metadata")
        print()
        
        # Process files with progress bar
        with tqdm(total=len(media_files), desc="Setting metadata", unit="file") as pbar:
            for file_path in media_files:
                result, error = self.process_file(file_path)
                
                if result == 'success':
                    self.stats['processed'] += 1
                elif result == 'skipped':
                    self.stats['skipped'] += 1
                    if error and '--verbose' in sys.argv:
                        tqdm.write(f"Skipped: {error}")
                elif result == 'failed':
                    self.stats['failed'] += 1
                    tqdm.write(f"Failed: {file_path.name} - {error}")
                
                pbar.update(1)
        
        # Print summary
        print("\n" + "="*60)
        print("METADATA SETTING COMPLETE")
        print("="*60)
        print(f"Total files: {self.stats['total']}")
        print(f"Successfully processed: {self.stats['processed']}")
        print(f"Skipped: {self.stats['skipped']}")
        print(f"Failed: {self.stats['failed']}")
        print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description='Set EXIF metadata on Snapchat memories based on filenames',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s downloads/
  %(prog)s downloads/ --force
  %(prog)s path/to/memories --verbose

This script parses dates from filenames in the format:
  YYYY-MM-DD_HH-MM-SS_uniqueid.ext
  
For images (.jpg, .jpeg):
  - Sets EXIF DateTimeOriginal, DateTimeDigitized, and DateTime
  - Uses piexif library
  
For videos (.mp4, .mov):
  - Sets CreateDate, ModifyDate, and Media/Track dates
  - Requires exiftool to be installed
        """
    )
    
    parser.add_argument(
        'directory',
        help='Directory containing downloaded Snapchat memories'
    )
    
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force overwrite existing metadata (default: skip files with metadata)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show verbose output including skipped files'
    )
    
    args = parser.parse_args()
    
    # Validate directory exists
    if not os.path.exists(args.directory):
        print(f"Error: Directory not found: {args.directory}")
        sys.exit(1)
    
    if not os.path.isdir(args.directory):
        print(f"Error: Not a directory: {args.directory}")
        sys.exit(1)
    
    # Create and run metadata setter
    setter = SnapchatMetadataSetter(
        directory=args.directory,
        force=args.force
    )
    
    try:
        setter.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

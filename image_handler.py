"""
Image handling for MtgPng2Pdf.
"""

import os
import glob
import random
from collections import defaultdict
from typing import List, Dict, Optional

from web_utils import download_image, list_webdav_directory
from parsing_utils import parse_variant_filename

class ImageSource:
    """Wrapper class to handle both local files and web URLs uniformly"""
    def __init__(self, path_or_url: str, is_url: bool = False):
        self.original = path_or_url
        self.is_url = is_url
        self.local_path = None if is_url else path_or_url
        self.temp_file = None
    def get_local_path(self, debug: bool = False) -> Optional[str]:
        """Get a local file path, downloading if necessary"""
        if not self.is_url: return self.local_path
        if self.temp_file is None: self.temp_file = download_image(self.original, debug=debug)
        return self.temp_file
    def cleanup(self):
        """Clean up any temporary files"""
        if self.temp_file and os.path.exists(self.temp_file):
            try: os.remove(self.temp_file)
            except: pass
            self.temp_file = None
    def __del__(self): self.cleanup()

def discover_images(
    png_dir: Optional[str] = None,
    image_server_base_url: Optional[str] = None,
    image_server_path_prefix: str = "/local_art",
    debug: bool = False
) -> Dict[str, List[ImageSource]]:
    """
    Discover images from local directory or web server and group them by normalized card name.
    Returns a dictionary mapping a normalized card name to a list of all its ImageSource variants.
    """
    all_cards_map: Dict[str, List[ImageSource]] = defaultdict(list)
    
    def process_file(filename: str, source_path: str, is_url: bool):
        # Parse the filename to get the card's base name, which we use as the key.
        normalized_key, _, _ = parse_variant_filename(filename)
        
        if not normalized_key:
            if debug: print(f"DEBUG:   Could not determine a key for '{filename}', skipping.")
            return

        img_source = ImageSource(source_path, is_url=is_url)
        all_cards_map[normalized_key].append(img_source)
        if debug:
            print(f"DEBUG:   Mapped '{filename}' to key '{normalized_key}'")

    if image_server_base_url:
        # Web server mode
        if debug:
            print(f"DEBUG: Discovering images from web server: {image_server_base_url}")
            print(f"DEBUG: Image source path on server: {image_server_path_prefix}")
        
        files = list_webdav_directory(image_server_base_url, image_server_path_prefix, debug)
        
        for file_info in files:
            process_file(file_info['name'], file_info['href'], is_url=True)
    
    elif png_dir:
        # Local directory mode
        if debug:
            print(f"DEBUG: Scanning PNG directory '{png_dir}' for PNGs...")
        
        for ext in ("*.png", "*.PNG"):
            for filepath in glob.glob(os.path.join(png_dir, ext)):
                process_file(os.path.basename(filepath), filepath, is_url=False)

    # Shuffle each list of variants to ensure random selection is fair
    for key in all_cards_map:
        random.shuffle(all_cards_map[key])

    return all_cards_map

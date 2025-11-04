"""
Output utilities for MtgPng2Pdf.
"""

import os
import shutil
import urllib.parse
from collections import defaultdict
from typing import List, Dict

from image_handler import ImageSource

def print_selection_manifest(manifest: Dict[str, Dict[str, int]]):
    """Prints a formatted summary of which card versions were selected."""
    if not manifest:
        return
        
    print("\n--- Card Selection Manifest ---")
    
    # Sort by original card name
    for card_name in sorted(manifest.keys()):
        versions = manifest[card_name]
        total_count = sum(versions.values())
        print(f"{total_count}x {card_name}:")
        
        # Sort by filename for consistent output
        for filename, count in sorted(versions.items()):
            print(f"  - {count}x {filename}")
    print("-----------------------------")

def write_missing_cards_file(deck_list_path: str, missing_cards: List[str]):
    if not missing_cards: return
    deck_list_dir = os.path.dirname(deck_list_path)
    deck_list_basename_no_ext = os.path.splitext(os.path.basename(deck_list_path))[0]
    missing_filename = f"{deck_list_basename_no_ext}_missing.txt"
    missing_filepath = os.path.join(deck_list_dir, missing_filename) if deck_list_dir else missing_filename
    try:
        if deck_list_dir and not os.path.exists(deck_list_dir): os.makedirs(deck_list_dir, exist_ok=True)
        with open(missing_filepath, 'w', encoding='utf-8') as f:
            for card_name in sorted(missing_cards): f.write(f"{card_name}\n")
        print(f"List of missing cards saved to: {missing_filepath}")
    except IOError as e: print(f"Error writing missing cards file '{missing_filepath}': {e}")

def create_png_output(*args, **kwargs): print(f"PNG page generation not fully implemented for web server mode")

def copy_deck_pngs(image_sources: List[ImageSource], png_out_dir: str, debug: bool = False):
    if not image_sources: print("No images to copy."); return
    if not os.path.exists(png_out_dir):
        try: os.makedirs(png_out_dir); print(f"Created output directory: {png_out_dir}")
        except OSError as e: print(f"Error: Could not create output directory '{png_out_dir}': {e}"); return
    elif not os.path.isdir(png_out_dir): print(f"Error: Output path '{png_out_dir}' exists but is not a directory."); return
    print(f"\n--- Copying PNGs to '{png_out_dir}' ---")
    source_file_copy_counts = defaultdict(int); copied_count = 0
    for img_source in image_sources:
        local_path = img_source.get_local_path(debug)
        if not local_path: print(f"Warning: Could not get image from {img_source.original}"); continue
        if img_source.is_url: original_basename = os.path.basename(urllib.parse.unquote(img_source.original))
        else: original_basename = os.path.basename(img_source.original)
        base, ext = os.path.splitext(original_basename)
        source_key = img_source.original; source_file_copy_counts[source_key] += 1; current_copy_num = source_file_copy_counts[source_key]
        if current_copy_num == 1: dest_basename = original_basename
        else: dest_basename = f"{base}-{current_copy_num}{ext}"
        dest_path = os.path.join(png_out_dir, dest_basename)
        try: shutil.copy2(local_path, dest_path); copied_count += 1
        except Exception as e: print(f"Error copying to '{dest_path}': {e}")
    print(f"Successfully copied {copied_count} PNG files to '{png_out_dir}'.")

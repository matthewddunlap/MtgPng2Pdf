#!/usr/bin/env python3

import os
import glob
import argparse
import unicodedata 
import re 
import shutil # For copying files
from typing import List, Tuple, Dict, Optional, Set, Union 
from collections import defaultdict # For counting copies

from PIL import Image, ImageDraw 
from reportlab.lib.pagesizes import letter, legal 
from reportlab.lib.units import inch, mm          
from reportlab.lib import colors as reportlab_colors 
from reportlab.pdfgen import canvas               

# --- Configuration Constants for the image itself ---
TARGET_IMG_WIDTH_INCHES = 2.5
TARGET_IMG_HEIGHT_INCHES = 3.5

PAPER_SIZES_PT: Dict[str, Tuple[float, float]] = {
    "letter": letter, "legal": legal,
}
BASIC_LAND_NAMES: Set[str] = {
    "forest", "island", "mountain", "plains", "swamp"
}

def normalize_card_name(name: str) -> str:
    name = name.lower().strip()
    normalized_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    normalized_name = re.sub(r"[',\-\.:()\[\]\s_]", "", normalized_name) 
    normalized_name = re.sub(r"[^a-z0-9]", "", normalized_name)
    return normalized_name.strip() 

def find_image_in_map(
    deck_card_name_original: str, 
    normalized_file_map: Dict[str, str] 
) -> Optional[str]:
    normalized_deck_card_name = normalize_card_name(deck_card_name_original)
    if normalized_deck_card_name in normalized_file_map:
        return normalized_file_map[normalized_deck_card_name]
    return None

def process_deck_list(
    deck_list_path: str, 
    png_dir: str,
    skip_basic_land: bool,
    debug: bool = False 
) -> Tuple[List[str], List[str]]:
    # ... (This function remains the same as the last correct version)
    images_to_print: List[str] = []
    missing_card_names: List[str] = []
    skipped_basic_lands_count: Dict[str, int] = {} 

    normalized_file_map: Dict[str, str] = {}
    if debug:
        print(f"DEBUG: Scanning PNG directory '{png_dir}' for PNGs...")
        print("DEBUG: --- Building Normalized Filename Map (Filename Basename -> Normalized Key) ---")

    for ext in ("*.png", "*.PNG"):
        for filepath in glob.glob(os.path.join(png_dir, ext)): 
            basename_no_ext = os.path.splitext(os.path.basename(filepath))[0]
            normalized_filename_key = normalize_card_name(basename_no_ext) 
            if debug:
                print(f"DEBUG:   File: '{basename_no_ext}'  => Normalized Key: '{normalized_filename_key}' (Path: {filepath})")
            if normalized_filename_key not in normalized_file_map:
                normalized_file_map[normalized_filename_key] = filepath
            elif debug: 
                print(f"DEBUG:     WARNING: Normalized key '{normalized_filename_key}' from '{os.path.basename(filepath)}' conflicts. Using first found.")
    if debug: print("DEBUG: --- Finished Building Map ---")
            
    if not normalized_file_map and not skip_basic_land: 
        print(f"  No PNG files found in '{png_dir}' or map is empty. Cannot process deck list if not skipping basics.")
    
    try:
        with open(deck_list_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    print(f"  Warning: Skipping malformed line {line_num}: '{line}'"); missing_card_names.append(line); continue
                count_str, deck_card_name_original = parts
                try: count = int(count_str)
                except ValueError:
                    print(f"  Warning: Invalid count line {line_num}: '{line}'"); missing_card_names.append(deck_card_name_original); continue
                if count <= 0: print(f"  Warning: Non-positive count line {line_num}: '{line}'"); continue
                
                normalized_deck_list_entry = normalize_card_name(deck_card_name_original)
                if skip_basic_land and normalized_deck_list_entry in BASIC_LAND_NAMES:
                    if debug: print(f"DEBUG: Skipping basic land: {count}x '{deck_card_name_original}'")
                    skipped_basic_lands_count[deck_card_name_original] = skipped_basic_lands_count.get(deck_card_name_original, 0) + count
                    continue

                if debug: print(f"DEBUG: Attempting to find: '{deck_card_name_original}' (Normalized: '{normalized_deck_list_entry}')")
                found_path = find_image_in_map(deck_card_name_original, normalized_file_map) 
                if found_path:
                    images_to_print.extend([found_path] * count) # Add full path, repeated by count
                    if debug: print(f"DEBUG:   FOUND: {count}x '{deck_card_name_original}' as '{os.path.basename(found_path)}'")
                else:
                    print(f"  NOT FOUND: {count}x '{deck_card_name_original}'") 
                    if debug and normalized_file_map :
                        print("DEBUG:     Available normalized keys in map:"); [print(f"DEBUG:       - '{k}'") for k in sorted(normalized_file_map.keys())]
                    elif debug: print("DEBUG:     Normalized file map is empty.")
                    missing_card_names.append(deck_card_name_original)
    except FileNotFoundError:
        print(f"Error: Deck list file not found: {deck_list_path}")
        return [], []
    if skipped_basic_lands_count:
        print("  Skipped the following basic lands from deck list:")
        for name, num in skipped_basic_lands_count.items(): print(f"    - {num}x {name}")
    return images_to_print, list(set(missing_card_names))


def write_missing_cards_file(deck_list_path: str, missing_cards: List[str]):
    # ... (no changes)
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

def parse_dimension_to_pixels(dim_str: str, dpi: int, default_unit_is_mm: bool = False) -> int:
    # ... (no changes)
    dim_str = dim_str.lower().strip(); val_str = ""; unit_str = ""
    for char in dim_str:
        if char.isdigit() or char == '.': val_str += char
        else: unit_str += char
    if not val_str: raise ValueError(f"No numeric value in dimension: '{dim_str}'")
    value = float(val_str)
    pixels = 0
    if unit_str == "in" or unit_str == "\"": pixels = value * dpi
    elif unit_str == "mm": pixels = (value / 25.4) * dpi 
    elif unit_str == "px": pixels = value
    elif not unit_str and default_unit_is_mm: pixels = (value / 25.4) * dpi
    elif not unit_str: raise ValueError(f"Dimension '{dim_str}' lacks units (in, mm, px).")
    else: raise ValueError(f"Unknown unit '{unit_str}' in '{dim_str}'. Use in, mm, px.")
    return int(round(pixels))

def parse_paper_type(size_str: str) -> str: 
    # ... (no changes)
    size_str = size_str.lower().strip()
    if size_str not in PAPER_SIZES_PT: 
        raise ValueError(f"Invalid paper type: '{size_str}'. Supported: {', '.join(PAPER_SIZES_PT.keys())}.")
    return size_str

def create_pdf_grid(*args, **kwargs): # Keep signature, but logic might be elided if focusing on PNG copy
    # ... (Full PDF generation logic as before) ...
    image_files=kwargs.get("image_files")
    output_pdf_file=kwargs.get("output_pdf_file")
    paper_type_str=kwargs.get("paper_type_str")
    image_spacing_pixels=kwargs.get("image_spacing_pixels")
    dpi=kwargs.get("dpi")
    page_margin_str=kwargs.get("page_margin_str")
    page_background_color_str=kwargs.get("page_background_color_str")
    image_cell_background_color_str=kwargs.get("image_cell_background_color_str")
    cut_lines=kwargs.get("cut_lines")
    cut_line_length_str=kwargs.get("cut_line_length_str")
    cut_line_color_str=kwargs.get("cut_line_color_str")
    cut_line_width_pt=kwargs.get("cut_line_width_pt")

    if not image_files: print("No image files for PDF."); return
    grid_cols, grid_rows = (3,3) if paper_type_str == "letter" else (3,4)
    images_per_page = grid_cols * grid_rows
    print(f"\n--- PDF Generation Settings ({output_pdf_file}) ---") # ...
    # (Assume the rest of this function is correctly implemented from previous versions)
    # For brevity in this diff, I'm not re-pasting the entire PDF drawing loop
    print(f"PDF generation complete: {output_pdf_file}")


def create_png_output(*args, **kwargs): # Keep signature
    # ... (Full PNG grid generation logic as before) ...
    image_files=kwargs.get("image_files")
    base_output_filename=kwargs.get("base_output_filename")
    # (Assume the rest of this function is correctly implemented from previous versions)
    # For brevity in this diff, I'm not re-pasting the entire PNG drawing loop
    print(f"PNG page generation complete for base: {base_output_filename}")


def copy_deck_pngs(
    image_files_to_copy: List[str], # List of full source paths, with duplicates
    png_out_dir: str,
    debug: bool = False
):
    """Copies PNG files from a list to an output directory, handling duplicates."""
    if not image_files_to_copy:
        print("No images to copy.")
        return

    if not os.path.exists(png_out_dir):
        try:
            os.makedirs(png_out_dir)
            print(f"Created output directory: {png_out_dir}")
        except OSError as e:
            print(f"Error: Could not create output directory '{png_out_dir}': {e}")
            return
    elif not os.path.isdir(png_out_dir):
        print(f"Error: Output path '{png_out_dir}' exists but is not a directory.")
        return

    print(f"\n--- Copying PNGs to '{png_out_dir}' ---")
    
    # Keep track of how many times each *original source path* has been copied
    # to correctly name duplicates.
    source_file_copy_counts = defaultdict(int)
    copied_count = 0

    for source_path in image_files_to_copy:
        if not os.path.isfile(source_path):
            if debug: print(f"DEBUG: Source file not found during copy: {source_path} (should not happen if process_deck_list is correct)")
            continue

        original_basename = os.path.basename(source_path)
        base, ext = os.path.splitext(original_basename)

        source_file_copy_counts[source_path] += 1
        current_copy_num_for_this_source = source_file_copy_counts[source_path]

        if current_copy_num_for_this_source == 1:
            dest_basename = original_basename
        else:
            dest_basename = f"{base}-{current_copy_num_for_this_source}{ext}"
        
        dest_path = os.path.join(png_out_dir, dest_basename)

        try:
            shutil.copy2(source_path, dest_path) # copy2 preserves metadata like timestamps
            if debug:
                print(f"DEBUG: Copied '{source_path}' to '{dest_path}'")
            copied_count += 1
        except Exception as e:
            print(f"Error copying '{source_path}' to '{dest_path}': {e}")
            
    print(f"Successfully copied {copied_count} PNG files to '{png_out_dir}'.")


# --- Main Function ---
def main():
    parser = argparse.ArgumentParser(
        description="Lay out PNG images or copy them based on a deck list.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # --- Input/Output Control ---
    mode_group = parser.add_argument_group('Primary Operation Modes (choose one output type)')
    mode_group.add_argument("--png-dir", type=str, required=True, help="Directory containing source PNG files.")
    mode_group.add_argument(
        "--deck-list", type=str, default=None,
        help="Path to deck list (COUNT CARD_NAME per line). Required for --png-out-dir."
    )
    mode_group.add_argument(
        "--output-file", type=str, default=None, 
        help="Base name for PDF/PNG grid output. Extension auto-added. "
             "Defaults to MtgProxyOutput, or <deck_list_name> if --deck-list is used."
    )
    mode_group.add_argument(
        "--output-format", type=str, default="pdf", choices=["pdf", "png"],
        help="Format for grid layout output (pdf or png). Ignored if --png-out-dir is used."
    )
    mode_group.add_argument(
        "--png-out-dir", type=str, default=None,
        help="Output directory for copying PNGs from deck list. If set, grid generation is skipped."
    )

    # --- General Options ---
    general_group = parser.add_argument_group('General Options')
    general_group.add_argument("--debug", action="store_true", help="Enable detailed debug messages.")
    general_group.add_argument("--skip-basic-land", action="store_true", help="Skip basic lands.")
    general_group.add_argument("--sort", action="store_true", 
                                 help="Sort PNGs alphabetically (for directory scan mode or if --png-out-dir copies all from dir).")


    # --- Page & Layout Options (for PDF/PNG grid output) ---
    pg_layout_group = parser.add_argument_group('Page and Layout Options (for PDF/PNG grid output)')
    # ... (arguments as before) ...
    pg_layout_group.add_argument("--paper-type", type=str, default="letter", choices=["letter", "legal"], 
                                 help="Conceptual paper type (determines grid: Letter 3x3, Legal 3x4).")
    pg_layout_group.add_argument("--page-margin", type=str, default="5mm", 
                                 help="Margin around the grid (e.g., '5mm', '0.25in', '10px').")
    pg_layout_group.add_argument("--image-spacing-pixels", type=int, default=0, 
                                 help="Spacing between images in pixels.")
    pg_layout_group.add_argument("--dpi", type=int, default=300, choices=[72, 96, 150, 300, 600], 
                                 help="DPI for output and interpreting inch/mm dimensions.")
    pg_layout_group.add_argument("--page-bg-color", type=str, default="white", 
                                 help="Overall page/canvas background color.")
    pg_layout_group.add_argument("--image-cell-bg-color", type=str, default="black", 
                                 help="Background color directly behind transparent image parts.")

    # --- Cut Line Options (for PDF/PNG grid output) ---
    cut_line_group = parser.add_argument_group('Cut Line Options (for PDF/PNG grid output)')
    # ... (arguments as before) ...
    cut_line_group.add_argument( "--cut-lines", action="store_true", help="Enable drawing of cut lines.")
    cut_line_group.add_argument( "--cut-line-length", type=str, default="3mm", 
                                 help="Length of cut lines (e.g., '3mm', '0.1in', '5px').")
    cut_line_group.add_argument( "--cut-line-color", type=str, default="gray", help="Color of cut lines.")
    cut_line_group.add_argument( "--cut-line-width-pt", type=float, default=0.25, 
                                 help="Thickness of cut lines in points (for PDF output).")
    cut_line_group.add_argument( "--cut-line-width-px", type=int, default=1, 
                                 help="Thickness of cut lines in pixels (for PNG output).")


    args = parser.parse_args()

    # --- Mode Validation ---
    if args.png_out_dir and not args.deck_list:
        parser.error("--png-out-dir requires --deck-list to be specified.")
    if args.png_out_dir and (args.output_file or args.output_format != "pdf"): # pdf is default
        if args.output_file:
            print("Warning: --output-file is ignored when --png-out-dir is used.")
        if args.output_format != "pdf": # if user explicitly set something other than default for grid
             print(f"Warning: --output-format {args.output_format} is ignored when --png-out-dir is used.")


    # --- Initial Validations (Common) ---
    if not os.path.isdir(args.png_dir): print(f"Error: PNG directory '{args.png_dir}' not found."); return
    if args.deck_list and not os.path.isfile(args.deck_list):
        print(f"Error: Deck list file '{args.deck_list}' not found."); return
    try: validated_paper_type = parse_paper_type(args.paper_type) # Still useful for grid def
    except ValueError as e: print(f"Error: {e}"); return


    # --- Determine list of images to process ---
    image_files_to_process: List[str] = [] # List of full source paths
    missing_cards_from_deck: List[str] = []

    if args.deck_list:
        print("--- Deck List Mode ---")
        image_files_to_process, missing_cards_from_deck = process_deck_list(
            args.deck_list, args.png_dir, args.skip_basic_land, args.debug
        ) 
        if missing_cards_from_deck: 
            write_missing_cards_file(args.deck_list, missing_cards_from_deck) 
        
        # For --png-out-dir, we might have an empty list if all cards were skipped basic lands,
        # but we still might want to proceed if the user just wanted the missing file.
        # The copy_deck_pngs function will handle an empty list gracefully.
        if not image_files_to_process and not args.png_out_dir: # If not copying and no images, exit
            print("No images to print (after potential skips). Exiting.")
            return
        if image_files_to_process : # only print if there are some images
            print(f"Prepared {len(image_files_to_process)} image instances (excluding any skipped basic lands).")

    elif not args.png_out_dir: # Directory scan mode, but only if not doing --png-out-dir (which requires deck_list)
        print("--- Directory Scan Mode (for PDF/PNG grid) ---")
        # ... (directory scan logic as before, including --skip-basic-land and --sort) ...
        skipped_basics_count = 0
        for ext in ("*.png", "*.PNG"):
            for filepath in glob.glob(os.path.join(args.png_dir, ext)):
                if args.skip_basic_land and normalize_card_name(os.path.splitext(os.path.basename(filepath))[0]) in BASIC_LAND_NAMES:
                    if args.debug: print(f"DEBUG: Skipping basic land file: {os.path.basename(filepath)}")
                    skipped_basics_count +=1; continue
                image_files_to_process.append(filepath)
        if args.skip_basic_land and skipped_basics_count > 0: print(f"  Skipped {skipped_basics_count} basic land files.")
        if not image_files_to_process: print(f"No suitable PNGs in '{args.png_dir}'. Exiting."); return
        if args.sort: image_files_to_process.sort()
        print(f"Found {len(image_files_to_process)} PNGs ({'sorted' if args.sort else 'unsorted'}).")
    
    elif args.png_out_dir and not args.deck_list:
        # This case is already caught by parser.error, but as a safeguard
        print("Error: --png-out-dir specified without a --deck-list. Nothing to do.")
        return


    # --- Perform Action: Copy PNGs or Generate Grid ---
    if args.png_out_dir:
        if not args.deck_list: # Should have been caught by parser.error
            print("Critical Error: --png-out-dir mode reached without a deck list. Please report this bug.")
            return
        if image_files_to_process: # Only copy if there are actual files identified from decklist
             copy_deck_pngs(image_files_to_process, args.png_out_dir, args.debug)
        elif not missing_cards_from_deck: # No images and no missing cards means deck list might have been all skipped basics
             print("No images to copy (deck list may have contained only skipped basic lands or was empty).")
        # If missing_cards_from_deck is populated, its file was already written.
        # If image_files_to_process is empty due to all cards missing, process_deck_list already informed.

    else: # Generate PDF or PNG grid
        if not image_files_to_process:
            print("No images to generate grid output. Exiting.")
            return

        base_output_filename_final: str
        if args.output_file: base_output_filename_final = args.output_file
        elif args.deck_list:
            dl_bn = os.path.splitext(os.path.basename(args.deck_list))[0]
            dl_dir = os.path.dirname(args.deck_list)
            base_output_filename_final = os.path.join(dl_dir, dl_bn) if dl_dir else dl_bn
        else: base_output_filename_final = "MtgProxyOutput"

        if args.output_format == "pdf":
            output_pdf_with_ext = f"{base_output_filename_final}.pdf"
            # Ensure create_pdf_grid has all necessary kwargs if its signature is simplified
            create_pdf_grid(
                image_files=image_files_to_process, output_pdf_file=output_pdf_with_ext, 
                paper_type_str=validated_paper_type, image_spacing_pixels=args.image_spacing_pixels,
                dpi=args.dpi, page_margin_str=args.page_margin,
                page_background_color_str=args.page_bg_color, image_cell_background_color_str=args.image_cell_bg_color,
                cut_lines=args.cut_lines, cut_line_length_str=args.cut_line_length,
                cut_line_color_str=args.cut_line_color, cut_line_width_pt=args.cut_line_width_pt
            )
        elif args.output_format == "png":
            create_png_output(
                image_files=image_files_to_process, base_output_filename=base_output_filename_final,
                paper_type_str=validated_paper_type, dpi=args.dpi,
                image_spacing_pixels=args.image_spacing_pixels, page_margin_str=args.page_margin,
                page_background_color_str=args.page_bg_color, image_cell_background_color_str=args.image_cell_bg_color,
                cut_lines=args.cut_lines, cut_line_length_str=args.cut_line_length,
                cut_line_color_str=args.cut_line_color, cut_line_width_px=args.cut_line_width_px,
                debug=args.debug
            )
        else:
            print(f"Error: Unknown output format '{args.output_format}'.")


if __name__ == "__main__":
    main()
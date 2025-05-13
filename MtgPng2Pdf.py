#!/usr/bin/env python3

import os
import glob
import argparse
import unicodedata 
import re 
from typing import List, Tuple, Dict, Optional

from PIL import Image 
from reportlab.lib.pagesizes import letter, legal
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# --- Configuration Constants for the image itself ---
TARGET_IMG_WIDTH_INCHES = 2.5
TARGET_IMG_HEIGHT_INCHES = 3.5

# Standard paper sizes in points (1 inch = 72 points)
PAPER_SIZES_PT: Dict[str, Tuple[float, float]] = {
    "letter": letter,
    "legal": legal,
}

def normalize_card_name(name: str) -> str:
    """
    Aggressively normalizes a card name for matching:
    - Converts to lowercase.
    - Removes accents and common diacritics.
    - Removes ALL common punctuation (apostrophes, commas, hyphens, underscores etc.).
    - Removes ALL spaces.
    - Strips leading/trailing whitespace (mostly for safety, space removal is key).
    """
    name = name.lower().strip()
    normalized_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    normalized_name = re.sub(r"[',\-\.:()\[\]\s_]", "", normalized_name) 
    normalized_name = re.sub(r"[^a-z0-9]", "", normalized_name)
    return normalized_name.strip() 

def find_image_in_map(
    deck_card_name_original: str, 
    normalized_file_map: Dict[str, str] 
) -> Optional[str]:
    """
    Tries to find the card in the pre-built map of normalized filenames.
    Relies on the aggressive normalize_card_name function.
    """
    normalized_deck_card_name = normalize_card_name(deck_card_name_original)
    
    if normalized_deck_card_name in normalized_file_map:
        return normalized_file_map[normalized_deck_card_name]
            
    return None

def process_deck_list(
    deck_list_path: str, 
    png_dir: str,
    debug: bool = False # Added debug flag
) -> Tuple[List[str], List[str]]:
    images_to_print: List[str] = []
    missing_card_names: List[str] = []
    
    normalized_file_map: Dict[str, str] = {}
    if debug:
        print(f"DEBUG: Scanning PNG directory '{png_dir}' for PNGs...")
        print("DEBUG: --- Building Normalized Filename Map (Filename Basename -> Normalized Key) ---")
    else:
        print(f"Scanning PNG directory '{png_dir}' for PNGs...")


    for ext in ("*.png", "*.PNG"):
        for filepath in glob.glob(os.path.join(png_dir, ext)): 
            basename_no_ext = os.path.splitext(os.path.basename(filepath))[0]
            normalized_filename_key = normalize_card_name(basename_no_ext) 
            
            if debug:
                print(f"DEBUG:   File: '{basename_no_ext}'  => Normalized Key: '{normalized_filename_key}' (Path: {filepath})")

            if normalized_filename_key not in normalized_file_map:
                normalized_file_map[normalized_filename_key] = filepath
            elif debug: # Only print warning in debug mode to avoid clutter
                print(f"DEBUG:     WARNING: Normalized key '{normalized_filename_key}' from '{os.path.basename(filepath)}' conflicts with existing entry for '{os.path.basename(normalized_file_map[normalized_filename_key])}'. Using first one found.")
    
    if debug:
        print("DEBUG: --- Finished Building Map ---")
            
    if not normalized_file_map:
        print(f"  No PNG files found in '{png_dir}' or map is empty. Cannot process deck list.")
        try:
            with open(deck_list_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    parts = line.split(maxsplit=1)
                    missing_card_names.append(parts[1] if len(parts) == 2 else line)
            return [], list(set(missing_card_names))
        except FileNotFoundError:
            print(f"Error: Deck list file not found: {deck_list_path}")
            return [], []

    if debug:
        print(f"DEBUG: Processing deck list: {deck_list_path}")
    else:
        print(f"Processing deck list: {deck_list_path}")

    try:
        with open(deck_list_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    print(f"  Warning: Skipping malformed line {line_num}: '{line}'")
                    missing_card_names.append(line) 
                    continue
                count_str, deck_card_name_original = parts
                try:
                    count = int(count_str)
                    if count <= 0: 
                        print(f"  Warning: Skipping line {line_num} with non-positive count: '{line}'")
                        continue
                except ValueError:
                    print(f"  Warning: Skipping malformed line {line_num} in deck list (invalid count): '{line}'")
                    missing_card_names.append(deck_card_name_original) 
                    continue
                
                if debug:
                    normalized_deck_list_entry = normalize_card_name(deck_card_name_original)
                    print(f"DEBUG: \n  Attempting to find: '{deck_card_name_original}' (Normalized attempt: '{normalized_deck_list_entry}')")

                found_path = find_image_in_map(deck_card_name_original, normalized_file_map) 
                
                if found_path:
                    images_to_print.extend([found_path] * count)
                    if debug: # Only print "Found" in debug mode
                        print(f"DEBUG:     FOUND: {count}x '{deck_card_name_original}' as '{os.path.basename(found_path)}'")
                else:
                    # "NOT FOUND" is important user feedback, always print
                    print(f"  NOT FOUND: {count}x '{deck_card_name_original}'") 
                    if debug:
                        if not normalized_file_map:
                            print("DEBUG:       Normalized file map is empty.")
                        else:
                            print("DEBUG:       Available normalized keys in map:")
                            for key_in_map in sorted(normalized_file_map.keys()): 
                                print(f"DEBUG:         - '{key_in_map}' (Points to: {os.path.basename(normalized_file_map[key_in_map])})")
                    missing_card_names.append(deck_card_name_original)
    except FileNotFoundError:
        print(f"Error: Deck list file not found: {deck_list_path}")
        return [], []
    return images_to_print, list(set(missing_card_names))

def write_missing_cards_file(deck_list_path: str, missing_cards: List[str]):
    if not missing_cards:
        return
    
    deck_list_dir = os.path.dirname(deck_list_path)
    deck_list_basename_no_ext = os.path.splitext(os.path.basename(deck_list_path))[0]
    
    missing_filename = f"{deck_list_basename_no_ext}_missing.txt"
    missing_filepath = os.path.join(deck_list_dir, missing_filename) if deck_list_dir else missing_filename

    try:
        if deck_list_dir and not os.path.exists(deck_list_dir):
            os.makedirs(deck_list_dir, exist_ok=True)
            
        with open(missing_filepath, 'w', encoding='utf-8') as f:
            for card_name in sorted(missing_cards):
                f.write(f"{card_name}\n")
        print(f"List of missing cards saved to: {missing_filepath}")
    except IOError as e:
        print(f"Error writing missing cards file '{missing_filepath}': {e}")

def parse_dimension(dim_str: str, default_unit_is_mm: bool = False) -> float:
    dim_str = dim_str.lower().strip()
    val_str = ""
    unit_str = ""
    for char in dim_str:
        if char.isdigit() or char == '.': val_str += char
        else: unit_str += char
    if not val_str: raise ValueError(f"No numeric value in dimension: '{dim_str}'")
    value = float(val_str)
    if unit_str == "in" or unit_str == "\"": return value * inch
    elif unit_str == "mm": return value * mm
    elif unit_str == "pt": return value
    elif not unit_str and default_unit_is_mm: return value * mm
    elif not unit_str: raise ValueError(f"Dimension '{dim_str}' lacks units (in, mm, pt).")
    else: raise ValueError(f"Unknown unit '{unit_str}' in '{dim_str}'. Use in, mm, pt.")

def parse_paper_type(size_str: str) -> str:
    size_str = size_str.lower().strip()
    if size_str not in PAPER_SIZES_PT:
        raise ValueError(f"Invalid paper type: '{size_str}'. Supported: {', '.join(PAPER_SIZES_PT.keys())}.")
    return size_str

def parse_color(color_str: str) -> colors.Color:
    color_str_lower = color_str.lower()
    if hasattr(colors, color_str_lower): return getattr(colors, color_str_lower)
    elif color_str.startswith('#') and (len(color_str) == 7 or len(color_str) == 9):
        try: return colors.HexColor(color_str)
        except Exception as e: raise ValueError(f"Invalid hex color '{color_str}'. {e}") from e
    raise ValueError(f"Invalid color '{color_str}'. Use ReportLab name or hex.")


def create_pdf_grid(
    image_files: List[str],
    output_pdf_file: str, 
    paper_type_str: str = "letter",
    image_spacing_pixels: int = 0,
    dpi: int = 300,
    page_margin_str: str = "5mm",
    page_background_color_str: str = "white",
    image_cell_background_color_str: str = "black",
    cut_lines: bool = False,
    cut_line_length_str: str = "3mm",
    cut_line_color_str: str = "gray",
    cut_line_width_pt: float = 0.25,
):
    if not image_files:
        print("No image files to process for PDF. PDF will not be generated.")
        return

    grid_cols: int; grid_rows: int
    if paper_type_str == "letter": grid_cols, grid_rows = 3, 3
    elif paper_type_str == "legal": grid_cols, grid_rows = 3, 4
    else:
        print(f"Error: Internal - unsupported paper type '{paper_type_str}'.")
        return
    images_per_page = grid_cols * grid_rows
    
    print(f"\n--- PDF Generation Settings ---")
    print(f"Selected paper type: {paper_type_str.capitalize()} (Grid: {grid_cols}x{grid_rows}, {images_per_page} images/page)")

    try:
        paper_width_pt, paper_height_pt = PAPER_SIZES_PT[paper_type_str]
        page_background_color = parse_color(page_background_color_str)
        image_cell_background_color = parse_color(image_cell_background_color_str)
        page_margin_pt = parse_dimension(page_margin_str, default_unit_is_mm=True)
    except (ValueError, KeyError) as e:
        print(f"Error parsing PDF configuration: {e}")
        return

    cut_line_len_pt = 0; parsed_cut_line_color = colors.gray
    if cut_lines:
        try:
            cut_line_len_pt = parse_dimension(cut_line_length_str, default_unit_is_mm=True)
            parsed_cut_line_color = parse_color(cut_line_color_str)
        except ValueError as e: print(f"Error parsing cut line options: {e}"); return

    image_spacing_pt = (image_spacing_pixels / dpi) * inch if dpi > 0 else 0
    target_img_width_pt = TARGET_IMG_WIDTH_INCHES * inch
    target_img_height_pt = TARGET_IMG_HEIGHT_INCHES * inch

    drawable_width_pt = paper_width_pt - (2 * page_margin_pt)
    drawable_height_pt = paper_height_pt - (2 * page_margin_pt)
    grid_content_width_pt = (grid_cols * target_img_width_pt) + ((grid_cols - 1) * image_spacing_pt)
    grid_content_height_pt = (grid_rows * target_img_height_pt) + ((grid_rows - 1) * image_spacing_pt)

    print(f"Output PDF: {output_pdf_file}") 
    print(f"Paper dimensions: {paper_width_pt/inch:.2f}in x {paper_height_pt/inch:.2f}in (Portrait)")
    print(f"Page margins: {page_margin_str} ({page_margin_pt:.2f}pt)")
    print(f"Image spacing: {image_spacing_pixels}px @ {dpi}DPI ({image_spacing_pt:.2f}pt)")
    print(f"Page background color: {page_background_color_str}")
    print(f"Image cell background color: {image_cell_background_color_str}")
    print(f"Target image size on paper: {TARGET_IMG_WIDTH_INCHES}\" x {TARGET_IMG_HEIGHT_INCHES}\"")
    if cut_lines: print(f"Cut lines: Enabled (Length: {cut_line_length_str}, Color: {cut_line_color_str}, Width: {cut_line_width_pt}pt)")
    else: print("Cut lines: Disabled")

    if grid_content_width_pt > drawable_width_pt or grid_content_height_pt > drawable_height_pt:
        print("Warning: Configured grid/spacing/margins may exceed paper's drawable area.")

    c = canvas.Canvas(output_pdf_file, pagesize=(paper_width_pt, paper_height_pt)) 
    num_images_total = len(image_files)
    generated_page_count = 0

    for i in range(0, num_images_total, images_per_page):
        page_images = image_files[i : i + images_per_page]
        generated_page_count += 1
        
        c.setFillColor(page_background_color); c.rect(0, 0, paper_width_pt, paper_height_pt, fill=1, stroke=0)
        grid_offset_x = (drawable_width_pt - grid_content_width_pt) / 2
        grid_offset_y = (drawable_height_pt - grid_content_height_pt) / 2
        grid_start_x_abs = page_margin_pt + grid_offset_x
        grid_start_y_abs = page_margin_pt + grid_offset_y
        image_positions_on_page = [] 

        for idx, image_path in enumerate(page_images):
            row_num = idx // grid_cols; col_num = idx % grid_cols
            x_pos = grid_start_x_abs + col_num * (target_img_width_pt + image_spacing_pt)
            y_pos = grid_start_y_abs + (grid_rows - 1 - row_num) * (target_img_height_pt + image_spacing_pt)
            image_positions_on_page.append((x_pos, y_pos))
            c.setFillColor(image_cell_background_color)
            c.rect(x_pos, y_pos, target_img_width_pt, target_img_height_pt, fill=1, stroke=0)
            try:
                c.drawImage(image_path, x_pos, y_pos, width=target_img_width_pt, height=target_img_height_pt, mask='auto')
            except Exception as e:
                print(f"Error drawing image {image_path}: {e}") 
                error_text_color = colors.white if image_cell_background_color.red<0.5 and image_cell_background_color.green<0.5 and image_cell_background_color.blue<0.5 else colors.black
                c.setFillColor(error_text_color)
                c.drawCentredString(x_pos + target_img_width_pt/2, y_pos + target_img_height_pt/2, "Error")

        if cut_lines: 
            c.setStrokeColor(parsed_cut_line_color); c.setLineWidth(cut_line_width_pt)
            for img_x,img_y in image_positions_on_page:
                w,h,cll = target_img_width_pt,target_img_height_pt,cut_line_len_pt
                c.line(img_x,img_y+h,img_x,img_y+h+cll); c.line(img_x+w,img_y+h,img_x+w,img_y+h+cll)
                c.line(img_x,img_y,img_x,img_y-cll); c.line(img_x+w,img_y,img_x+w,img_y-cll)
                c.line(img_x,img_y+h,img_x-cll,img_y+h); c.line(img_x,img_y,img_x-cll,img_y)
                c.line(img_x+w,img_y+h,img_x+w+cll,img_y+h); c.line(img_x+w,img_y,img_x+w+cll,img_y)
        c.showPage()
        print(f"  Generated page {generated_page_count} with {len(page_images)} images.")
    c.save()
    print(f"PDF generation complete: {output_pdf_file}") 


def main():
    parser = argparse.ArgumentParser(
        description="Lay out PNG images in a grid on PDF pages (Letter: 3x3, Legal: 3x4). Supports deck list input.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--png-dir", type=str, required=True, help="Directory containing PNG files.")
    parser.add_argument(
        "--pdf-file", type=str, default=None, 
        help="Output PDF. Defaults to MtgPng2Pdf.pdf, or <deck_list_name>.pdf if --deck-list used."
    )
    parser.add_argument(
        "--deck-list", type=str, default=None,
        help="Path to deck list (COUNT CARD_NAME per line). Processes only images from this list."
    )
    parser.add_argument( # New debug flag
        "--debug", action="store_true", help="Enable detailed debug messages for name matching."
    )
    
    pg_layout_group = parser.add_argument_group('Page and Layout Options')
    pg_layout_group.add_argument("--paper-type", type=str, default="letter", choices=["letter", "legal"], help="Paper type (Letter 3x3, Legal 3x4).")
    pg_layout_group.add_argument("--page-margin", type=str, default="5mm", help="Margin (e.g., '5mm', '0.25in').")
    pg_layout_group.add_argument("--image-spacing-pixels", type=int, default=0, help="Spacing between images in pixels.")
    pg_layout_group.add_argument("--dpi", type=int, default=300, choices=[72, 96, 150, 300, 600], help="DPI for pixel spacing.")
    pg_layout_group.add_argument("--page-bg-color", type=str, default="white", help="Overall page background color.")
    pg_layout_group.add_argument("--image-cell-bg-color", type=str, default="black", help="Background color behind transparent image parts.")
    pg_layout_group.add_argument("--sort", action="store_true", help="Sort PNGs alphabetically (ignored if --deck-list is used).")

    cut_line_group = parser.add_argument_group('Cut Line Options')
    cut_line_group.add_argument( "--cut-lines", action="store_true", help="Enable drawing of cut lines.")
    cut_line_group.add_argument( "--cut-line-length", type=str, default="3mm", help="Length of cut lines (e.g., '3mm', '0.1in').")
    cut_line_group.add_argument( "--cut-line-color", type=str, default="gray", help="Color of cut lines.")
    cut_line_group.add_argument( "--cut-line-width-pt", type=float, default=0.25, help="Thickness of cut lines in points.")

    args = parser.parse_args()

    output_pdf_final: str
    if args.pdf_file:
        output_pdf_final = args.pdf_file
    elif args.deck_list:
        deck_list_basename_no_ext = os.path.splitext(os.path.basename(args.deck_list))[0]
        deck_list_dir = os.path.dirname(args.deck_list)
        if deck_list_dir: 
             output_pdf_final = os.path.join(deck_list_dir, f"{deck_list_basename_no_ext}.pdf")
        else: 
            output_pdf_final = f"{deck_list_basename_no_ext}.pdf"
    else: 
        output_pdf_final = "MtgPng2Pdf.pdf"

    try: validated_paper_type = parse_paper_type(args.paper_type)
    except ValueError as e: print(f"Error: {e}"); return
    if not os.path.isdir(args.png_dir): print(f"Error: PNG directory '{args.png_dir}' not found."); return
    if args.deck_list and not os.path.isfile(args.deck_list):
        print(f"Error: Deck list file '{args.deck_list}' not found.")
        return

    image_files_to_process: List[str] = []
    missing_cards_from_deck: List[str] = []

    if args.deck_list:
        print("--- Deck List Mode ---")
        # Pass the debug flag to process_deck_list
        image_files_to_process, missing_cards_from_deck = process_deck_list(args.deck_list, args.png_dir, args.debug) 
        if missing_cards_from_deck:
            write_missing_cards_file(args.deck_list, missing_cards_from_deck) 
        if not image_files_to_process:
            print("No images found based on the deck list. Exiting.")
            return
        print(f"Prepared {len(image_files_to_process)} images for PDF based on deck list.")
    else:
        print("--- Directory Scan Mode ---")
        for ext in ("*.png", "*.PNG"):
            image_files_to_process.extend(glob.glob(os.path.join(args.png_dir, ext)))
        if not image_files_to_process:
            print(f"No PNG files found in '{args.png_dir}'. Exiting.")
            return
        if args.sort:
            image_files_to_process.sort()
        print(f"Found {len(image_files_to_process)} PNG files in directory ({'sorted' if args.sort else 'unsorted'}).")

    create_pdf_grid(
        image_files=image_files_to_process,
        output_pdf_file=output_pdf_final, 
        paper_type_str=validated_paper_type,
        image_spacing_pixels=args.image_spacing_pixels,
        dpi=args.dpi,
        page_margin_str=args.page_margin,
        page_background_color_str=args.page_bg_color,
        image_cell_background_color_str=args.image_cell_bg_color,
        cut_lines=args.cut_lines,
        cut_line_length_str=args.cut_line_length,
        cut_line_color_str=args.cut_line_color,
        cut_line_width_pt=args.cut_line_width_pt,
    )

if __name__ == "__main__":
    main()
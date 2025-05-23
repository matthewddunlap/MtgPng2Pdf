#!/usr/bin/env python3

import os
import glob
import argparse
import unicodedata
import re
import shutil # For copying files
from typing import List, Tuple, Dict, Optional, Set, Union, Any # Moved Any here
from collections import defaultdict # For counting copies
import math # For cameo PDF generation
import random

from PIL import Image, ImageDraw, ImageFont # Added ImageFont
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

# --- START: Cameo PDF Generation Code (Adapted from utilities.py and layouts.json) ---

# Embedded layouts.json content
# Extracted from the provided layouts.json file
LAYOUTS_DATA: Dict[str, Any] = {
    "paper_layouts": {
        "letter": {
            "width": 3300, # Native pixels, assume 300 DPI for these values
            "height": 2550,
            "card_layouts": {
                "standard": { # MTG card size
                    "width": 742, # Native pixels for card on page
                    "height": 1036,
                    "x_pos": [141, 900, 1658, 2417], # 4 cols in create_pdf.py's letter_standard_v3
                    "y_pos": [232, 1282],            # 2 rows in create_pdf.py's letter_standard_v3
                    "template": "letter_standard_v3"
                },
                "japanese": { # Example, not primary target for MTG
                    "width": 694, "height": 1015,
                    "x_pos": [165, 924, 1682, 2441], "y_pos": [243, 1293],
                    "template": "letter_japanese_v1"
                },
            }
        },
        "a4": { # Example for completeness, if MtgDeck2Print adds A4 support
            "width": 3508, "height": 2480,
            "card_layouts": {
                "standard": {
                    "width": 742, "height": 1036,
                    "x_pos": [245, 1004, 1763, 2522], "y_pos": [197, 1247],
                    "template": "a4_standard_v2"
                },
            }
        },
    }
}

class CameoPaperSize: # Simplified enum style
    LETTER = "letter"
    A4 = "a4"

class CameoCardSize: # Simplified enum style
    STANDARD = "standard"
    JAPANESE = "japanese"

def parse_basic_land_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    """
    Parses a basic land filename like 'Forest-avr-242.png' or 'Island-ZEN-123b.png'.
    Returns (land_type, set_code, unique_part) or None if not a match.
    Assumes basic land names are in BASIC_LAND_NAMES.
    """
    basename_no_ext = os.path.splitext(os.path.basename(filename))[0]
    parts = basename_no_ext.split('-')
    
    if len(parts) >= 3: # Expect at least Type-Set-Unique
        land_type_candidate = parts[0].lower()
        if land_type_candidate in BASIC_LAND_NAMES:
            set_code = parts[1].lower()
            # The rest is considered the unique part, even if it contains more hyphens
            unique_part = "-".join(parts[2:]) 
            return land_type_candidate, set_code, unique_part
    return None

def calculate_max_print_bleed_cameo(x_pos: List[int], y_pos: List[int], width: int, height: int) -> int:
    if len(x_pos) == 1 and len(y_pos) == 1:
        return 0

    x_border_max = 100000
    if len(x_pos) >= 2:
        sorted_x_pos = sorted(x_pos)
        x_pos_0 = sorted_x_pos[0]
        x_pos_1 = sorted_x_pos[1]
        x_border_max = math.ceil((x_pos_1 - x_pos_0 - width) / 2)
        if x_border_max < 0: x_border_max = 100000

    y_border_max = 100000
    if len(y_pos) >= 2:
        sorted_y_pos = sorted(y_pos)
        y_pos_0 = sorted_y_pos[0]
        y_pos_1 = sorted_y_pos[1]
        y_border_max = math.ceil((y_pos_1 - y_pos_0 - height) / 2)
        if y_border_max < 0: y_border_max = 100000
    
    return min(x_border_max, y_border_max) + 1


# --- MtgDeck2Print.py (Relevant Cameo PDF functions) ---

# ... (previous Cameo helper functions like calculate_max_print_bleed_cameo) ...

def draw_card_with_border_cameo(
    card_image: Image.Image, 
    base_image: Image.Image, 
    box: tuple[int, int, int, int], 
    print_bleed: int,
    cell_bg_color_pil: Union[str, Tuple[int, int, int], None] # NEW ARGUMENT
):
    origin_x, origin_y, origin_width, origin_height = box

    # --- NEW: Draw cell background first ---
    if cell_bg_color_pil is not None:
        # The cell background should cover the entire area of the card slot,
        # including the bleed area that will be drawn.
        # The largest extent of the bleed will be print_bleed pixels outwards from origin_width/height.
        # So, the cell rect starts at (origin_x - print_bleed, origin_y - print_bleed)
        # and has dimensions (origin_width + 2*print_bleed, origin_height + 2*print_bleed)
        # However, draw_card_with_border_cameo is called with `box` representing the card *without* bleed.
        # The bleed is added iteratively *inside* this function.
        # The cell background should be drawn *behind* the largest bleed iteration.
        # The largest bleed will extend `print_bleed-1` pixels beyond the `box`.
        # So the cell background should be at (origin_x - (print_bleed-1), origin_y - (print_bleed-1))
        # with size (origin_width + 2*(print_bleed-1), origin_height + 2*(print_bleed-1))
        # A simpler approach matching ReportLab: The cell_bg is for the card's final footprint.
        # The bleed is an extension of the card image itself.
        # So, the cell background is just the `box` dimensions.
        # Let's draw the cell background to match the card's final dimensions (box)
        # before any bleed is applied to the card image itself.
        
        # The cell background should be drawn based on the slot for the card,
        # not just the card image if it's smaller.
        # `box` defines where the card *image* (potentially resized) goes.
        # The underlying cell can be considered to be this box.
        
        draw = ImageDraw.Draw(base_image)
        # The cell background covers the area defined by 'box' arguments.
        # The bleed borders are drawn on top of this.
        cell_rect_x0 = origin_x
        cell_rect_y0 = origin_y
        cell_rect_x1 = origin_x + origin_width
        cell_rect_y1 = origin_y + origin_height
        
        # If print_bleed is > 0, the card will be drawn slightly outside this 'box'
        # The cell background should cover the full extent of the card including bleed.
        # The largest image drawn will be (origin_width + 2*(print_bleed-1)), (origin_height + 2*(print_bleed-1))
        # and pasted at (origin_x - (print_bleed-1)), (origin_y - (print_bleed-1))
        if print_bleed > 0: # If there's bleed, expand the cell background
            # We need to be careful here. The `box` is where the card *content* (sans bleed) is placed.
            # The bleed extends outwards from this. So the cell background should cover
            # the `box` plus the maximum bleed extent.
            # The `print_bleed` value here represents iterations.
            # The largest offset is `print_bleed - 1` if `print_bleed > 0`.
            max_offset = print_bleed -1 if print_bleed > 0 else 0
            cell_rect_x0 = origin_x - max_offset
            cell_rect_y0 = origin_y - max_offset
            cell_rect_x1 = origin_x + origin_width + max_offset
            cell_rect_y1 = origin_y + origin_height + max_offset

        draw.rectangle(
            [cell_rect_x0, cell_rect_y0, cell_rect_x1, cell_rect_y1],
            fill=cell_bg_color_pil
        )
    # --- END NEW ---

    for i in reversed(range(print_bleed)): # Iterates from largest bleed to smallest (actual card image)
        # card_image is the *original* card (after source cropping/extend_corners)
        # It gets resized here for each bleed iteration
        card_image_resized_for_this_iteration = card_image.resize(
            (origin_width + (2 * i), origin_height + (2 * i)) # No explicit filter
        )
        # Paste location is shifted outward by 'i' to center the bleed growth relative to the original box
        paste_pos_x = origin_x - i
        paste_pos_y = origin_y - i
        
        base_image.paste(
            card_image_resized_for_this_iteration, 
            (paste_pos_x, paste_pos_y), 
            card_image_resized_for_this_iteration if card_image_resized_for_this_iteration.mode == 'RGBA' else None
        )


def draw_card_layout_cameo(
    card_images: List[Image.Image], 
    base_image: Image.Image, 
    num_rows: int, num_cols: int, 
    x_pos_layout: List[int], y_pos_layout: List[int], 
    card_width_layout: int, card_height_layout: int, 
    print_bleed_layout_units: int,
    crop_percentage: float,
    ppi_ratio: float,
    extend_corners_src_px: int,
    flip: bool,
    cell_bg_color_pil: Union[str, Tuple[int, int, int], None] # NEW ARGUMENT
):
    num_slots_on_page = num_rows * num_cols

    for i, original_card_pil_image in enumerate(card_images):
        if i >= num_slots_on_page: break
        current_card_image = original_card_pil_image
        slot_x_on_page_scaled = math.floor(x_pos_layout[i % num_cols] * ppi_ratio)
        slot_y_on_page_scaled = math.floor(y_pos_layout[i // num_cols] * ppi_ratio)
        
        # ... (cropping and extend_corners logic for current_card_image remains the same) ...
        if crop_percentage > 0:
            card_w, card_h = current_card_image.size
            crop_w_px = math.floor(card_w / 2 * (crop_percentage / 100.0))
            crop_h_px = math.floor(card_h / 2 * (crop_percentage / 100.0))
            current_card_image = current_card_image.crop((crop_w_px, crop_h_px, card_w - crop_w_px, card_h - crop_h_px))

        if extend_corners_src_px > 0:
            current_card_image = current_card_image.crop((
                extend_corners_src_px, extend_corners_src_px, 
                current_card_image.width - extend_corners_src_px, 
                current_card_image.height - extend_corners_src_px
            ))
        
        extend_corners_page_px_scaled = math.floor(extend_corners_src_px * ppi_ratio)
        card_render_width_scaled = math.floor(card_width_layout * ppi_ratio) - (2 * extend_corners_page_px_scaled)
        card_render_height_scaled = math.floor(card_height_layout * ppi_ratio) - (2 * extend_corners_page_px_scaled)

        # This 'paste_box' is where the card *content* (scaled, after source cropping) will be drawn.
        # The bleed borders extend outwards from this box.
        paste_box_for_card_content = (
            slot_x_on_page_scaled + extend_corners_page_px_scaled, 
            slot_y_on_page_scaled + extend_corners_page_px_scaled, 
            card_render_width_scaled, 
            card_render_height_scaled
        )

        # This is the number of bleed border iterations.
        final_print_bleed_iterations = math.ceil(print_bleed_layout_units * ppi_ratio) + extend_corners_page_px_scaled
        
        draw_card_with_border_cameo(
            current_card_image, # This is the card image *after* source cropping
            base_image,
            paste_box_for_card_content, # Defines the core card content area
            final_print_bleed_iterations, # Number of 1px bleed borders to add
            cell_bg_color_pil # Pass the color
        )

def create_pdf_cameo_style(
    image_files: List[str],
    output_pdf_file: str,
    paper_type_arg: str,
    target_dpi: int,
    image_cell_bg_color_str: str,
    pdf_name_label: Optional[str],
    debug: bool = False
):
    # ... (initial prints and setup as before) ...
    print(f"\n--- Cameo PDF Generation (PIL-based) ---")
    print(f"Output file: {output_pdf_file}")
    # NEW: Print cell bg color if not default
    default_cell_bg_color = "black" # Assuming this was the implicit default
    if image_cell_bg_color_str.lower() != default_cell_bg_color:
        print(f"  Image Cell Background Color: {image_cell_bg_color_str}")

    cameo_paper_key: str
    if paper_type_arg.lower() == "letter":
        cameo_paper_key = CameoPaperSize.LETTER
    elif paper_type_arg.lower() == "a4": # If MtgDeck2Print were to support A4
        cameo_paper_key = CameoPaperSize.A4
    else:
        print(f"Error: --cameo PDF generation: Paper type '{paper_type_arg}' is not directly supported by embedded cameo layouts (which includes 'letter', 'a4').")
        if paper_type_arg.lower() == "legal":
             print(f"       Note: The 'legal' paper size is not defined in the source layouts.json used as a model for cameo mode.")
        return
    
    cameo_card_key = CameoCardSize.STANDARD # MTG cards use "standard" layout size

    try:
        paper_layout_config = LAYOUTS_DATA["paper_layouts"][cameo_paper_key]
        card_layout_config = paper_layout_config["card_layouts"][cameo_card_key]
    except KeyError:
        print(f"Error: Layout for paper '{cameo_paper_key}' and card size '{cameo_card_key}' not found in embedded layouts.")
        return

    num_rows = len(card_layout_config["y_pos"])
    num_cols = len(card_layout_config["x_pos"])
    num_cards_per_page = num_rows * num_cols
    layout_base_ppi = 300.0
    ppi_ratio = target_dpi / layout_base_ppi
    page_width_px_scaled = math.floor(paper_layout_config["width"] * ppi_ratio)
    page_height_px_scaled = math.floor(paper_layout_config["height"] * ppi_ratio)
    card_slot_width_layout = card_layout_config["width"]
    card_slot_height_layout = card_layout_config["height"]
    crop_percentage_on_source = 0.0
    extend_corners_on_source_px = 0
    pdf_save_quality = 75
    max_print_bleed_layout_units = calculate_max_print_bleed_cameo(
        card_layout_config["x_pos"], card_layout_config["y_pos"],
        card_slot_width_layout, card_slot_height_layout
    )

    if debug:
        print(f"DEBUG CAMEO: Paper Key: {cameo_paper_key}, Card Key: {cameo_card_key}")
        print(f"DEBUG CAMEO: Layout Page Dim (WxH @{layout_base_ppi}PPI): {paper_layout_config['width']}x{paper_layout_config['height']}")
        print(f"DEBUG CAMEO: Target DPI: {target_dpi}, PPI Ratio: {ppi_ratio:.4f}")
        print(f"DEBUG CAMEO: Output Page Dim (WxH @{target_dpi}PPI): {page_width_px_scaled}x{page_height_px_scaled}")
        print(f"DEBUG CAMEO: Layout Card Slot Dim (WxH @{layout_base_ppi}PPI): {card_slot_width_layout}x{card_slot_height_layout}")
        print(f"DEBUG CAMEO: Grid: {num_cols}x{num_rows} ({num_cards_per_page} cards/page)")
        print(f"DEBUG CAMEO: Max Print Bleed (layout units): {max_print_bleed_layout_units}")

    # --- START: NEW - Attempt to load registration mark image ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Assumes 'assets' is a subdirectory in the same location as MtgDeck2Print.py
    asset_dir_cameo = os.path.join(script_dir, "assets") 
    registration_filename = f'{cameo_paper_key}_registration.jpg' # e.g., letter_registration.jpg or a4_registration.jpg
    registration_path = os.path.join(asset_dir_cameo, registration_filename)
    
    master_page_background: Optional[Image.Image] = None
    if os.path.exists(registration_path):
        try:
            reg_im_original = Image.open(registration_path)
            # The registration image from utilities.py is designed for paper_layout_config width/height at layout_base_ppi (300).
            # We need to scale it to the target_dpi for our output page.
            reg_im_scaled = reg_im_original.resize((page_width_px_scaled, page_height_px_scaled)) # No explicit filter, matches utilities.py
            
            # Ensure the image is RGB for PDF saving, as registration marks are typically color/grayscale.
            if reg_im_scaled.mode != 'RGB':
                if reg_im_scaled.mode == 'L' or reg_im_scaled.mode == 'P': # Grayscale or Palette
                    reg_im_scaled = reg_im_scaled.convert('RGB')
                elif reg_im_scaled.mode == 'RGBA': # Has alpha (e.g. if a PNG registration mark was used)
                    # Create an RGB canvas and paste RGBA image onto it, effectively flattening alpha
                    rgb_canvas = Image.new("RGB", reg_im_scaled.size, "white") # Assume white for transparent parts
                    rgb_canvas.paste(reg_im_scaled, mask=reg_im_scaled.split()[3]) # Paste using alpha channel as mask
                    reg_im_scaled = rgb_canvas
                # Add other mode conversions if necessary, though JPGs are usually L or RGB.
            
            master_page_background = reg_im_scaled
            if debug: print(f"DEBUG CAMEO: Loaded and scaled registration mark image: {registration_path}")
        except Exception as e_reg:
            print(f"  Warning (Cameo): Could not load/process registration image '{registration_path}': {e_reg}. Falling back to white page background.")
    else:
        print(f"  Warning (Cameo): Registration mark image not found at '{registration_path}'. PDF pages will have a white background. For Cameo registration marks, ensure an 'assets' subdirectory exists next to the script, containing '{registration_filename}'.")

    if master_page_background is None: # Fallback if registration image failed to load
        master_page_background = Image.new("RGB", (page_width_px_scaled, page_height_px_scaled), "white")
    # --- END: NEW - Attempt to load registration mark image ---

    pil_cell_bg_color: Union[str, Tuple[int,int,int], None] = image_cell_bg_color_str
    
    all_pil_pages: List[Image.Image] = []
    total_images_to_process = len(image_files)

    for page_start_index in range(0, total_images_to_process, num_cards_per_page):
        # --- MODIFIED: Use master_page_background ---
        current_page_pil_image = master_page_background.copy() 

        image_paths_for_this_page = image_files[page_start_index : page_start_index + num_cards_per_page]
        pil_card_images_for_page: List[Image.Image] = []
        for img_path in image_paths_for_this_page:
            try:
                img = Image.open(img_path)
                img = img.convert('RGBA') # Ensure RGBA for consistent alpha handling for card paste
                pil_card_images_for_page.append(img)
            except Exception as e:
                print(f"  Warning (Cameo): Could not open/process image '{img_path}': {e}")
                placeholder_w = int(TARGET_IMG_WIDTH_INCHES * target_dpi) 
                placeholder_h = int(TARGET_IMG_HEIGHT_INCHES * target_dpi)
                placeholder = Image.new("RGBA", (placeholder_w, placeholder_h), (255, 192, 203, 255))
                draw_placeholder = ImageDraw.Draw(placeholder)
                # --- MODIFIED: More robust font loading for placeholder text ---
                try:
                    # Attempt to use a slightly more visible default font if possible
                    font_placeholder: Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
                    try: font_placeholder = ImageFont.truetype("arial.ttf", 15) # Small fixed size
                    except IOError: 
                        try: font_placeholder = ImageFont.truetype("DejaVuSans.ttf", 15)
                        except IOError: font_placeholder = ImageFont.load_default() 
                    draw_placeholder.text((5,5), "Error\nLoading", fill="black", font=font_placeholder)
                except Exception: # Fallback if any font loading fails
                    draw_placeholder.text((5,5), "Error", fill="black")
                pil_card_images_for_page.append(placeholder)
        
        draw_card_layout_cameo(
            card_images=pil_card_images_for_page,
            base_image=current_page_pil_image,
            num_rows=num_rows,
            num_cols=num_cols,
            x_pos_layout=card_layout_config["x_pos"],
            y_pos_layout=card_layout_config["y_pos"],
            card_width_layout=card_slot_width_layout,
            card_height_layout=card_slot_height_layout,
            print_bleed_layout_units=max_print_bleed_layout_units,
            crop_percentage=crop_percentage_on_source,
            ppi_ratio=ppi_ratio,
            extend_corners_src_px=extend_corners_on_source_px,
            flip=False,
            cell_bg_color_pil=pil_cell_bg_color # PASS THE NEW ARGUMENT
        )
        
        page_num_for_label = (page_start_index // num_cards_per_page) + 1

        template_name = card_layout_config.get("template", "unknown_template")

        # --- MODIFIED: Construct label_text with pdf_name_label ---
        base_label_part = f"template: {template_name}, sheet: {page_num_for_label}"
        if pdf_name_label: # If a name is provided
            label_text = f"name: {pdf_name_label}, {base_label_part}"
        else:
            label_text = base_label_part
        # --- END MODIFICATION ---

        try:
            draw_page_text = ImageDraw.Draw(current_page_pil_image)
            text_x_pos = math.floor((paper_layout_config["width"] - 180) * ppi_ratio)
            text_y_pos = math.floor((paper_layout_config["height"] - 180) * ppi_ratio)
            font_size_scaled = math.floor(40 * ppi_ratio) # Original was 40pt font @300DPI scale
            
            page_font: Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
            try: 
                page_font = ImageFont.truetype("arial.ttf", font_size_scaled)
            except IOError:
                try:
                    page_font = ImageFont.truetype("DejaVuSans.ttf", font_size_scaled)
                except IOError:
                    # --- MODIFIED: Try load_default with size if available (Pillow >= 9.2.0) ---
                    try:
                        page_font = ImageFont.load_default(size=font_size_scaled) 
                    except AttributeError: # Older Pillow: load_default() has no size param
                        page_font = ImageFont.load_default() 
            
            draw_page_text.text((text_x_pos, text_y_pos), label_text, fill=(0,0,0), anchor="ra", font=page_font)
        except Exception as e_font:
            if debug: print(f"DEBUG CAMEO: Could not draw page label: {e_font}")

        all_pil_pages.append(current_page_pil_image)

    if not all_pil_pages:
        print("Cameo PDF: No pages generated (no images provided or all failed to load).") # Slight wording adjustment
        return

    try:
        all_pil_pages[0].save(
            output_pdf_file,
            format='PDF',
            save_all=True,
            append_images=all_pil_pages[1:],
            resolution=float(target_dpi), 
            quality=pdf_save_quality      
        )
        print(f"Cameo PDF generation successful: {output_pdf_file} ({len(all_pil_pages)} page(s))")
    except Exception as e:
        print(f"Error saving Cameo PDF '{output_pdf_file}': {e}")

# --- END: Cameo PDF Generation Code ---


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

# Modified process_deck_list

def process_deck_list(
    deck_list_path: str,
    png_dir: str,
    skip_basic_land: bool,
    basic_land_sets_filter: Optional[List[str]], # NEW ARGUMENT
    debug: bool = False
) -> Tuple[List[str], List[str]]:
    images_to_print: List[str] = []
    missing_card_names: List[str] = []
    skipped_basic_lands_count: Dict[str, int] = {}

    # --- Data structures for card images ---
    # For non-basic lands (and as a fallback for basics if parsing fails)
    normalized_file_map: Dict[str, str] = {} 
    # For basic lands: Dict[land_type, List[Dict{'set': str, 'path': str, 'id': str}]]
    basic_land_details: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    if debug:
        print(f"DEBUG: Scanning PNG directory '{png_dir}' for PNGs...")
        print("DEBUG: --- Building Normalized Filename Map & Basic Land Details ---")
        if basic_land_sets_filter:
            print(f"DEBUG: Basic land set filter active: {basic_land_sets_filter}")

    for ext in ("*.png", "*.PNG"):
        for filepath in glob.glob(os.path.join(png_dir, ext)):
            basename_no_ext = os.path.splitext(os.path.basename(filepath))[0]
            
            # Attempt to parse as basic land first
            parsed_basic = parse_basic_land_filename(basename_no_ext)
            if parsed_basic:
                land_type, set_code, unique_id = parsed_basic
                basic_land_details[land_type].append({
                    'set': set_code, 
                    'path': filepath, 
                    'id': unique_id # For ensuring uniqueness if needed later
                })
                if debug:
                    print(f"DEBUG:   Basic Land Parsed: '{basename_no_ext}' -> Type: {land_type}, Set: {set_code}, Path: {filepath}")
            
            # Always add to the normalized_file_map for general lookup
            # This map is used for non-basics and as a fallback if basic land special handling fails.
            normalized_filename_key = normalize_card_name(basename_no_ext)
            if debug and not parsed_basic: # Only print general mapping if not already printed as basic
                print(f"DEBUG:   Non-Basic/Other: '{basename_no_ext}' => Normalized Key: '{normalized_filename_key}' (Path: {filepath})")
            
            if normalized_filename_key not in normalized_file_map:
                normalized_file_map[normalized_filename_key] = filepath
            elif debug:
                print(f"DEBUG:     WARNING: Normalized key '{normalized_filename_key}' from '{os.path.basename(filepath)}' conflicts. Using first found.")

    if debug: print("DEBUG: --- Finished Building Maps ---")

    if not normalized_file_map and not basic_land_details and not skip_basic_land:
        print(f"  No PNG files found in '{png_dir}' or maps are empty. Cannot process deck list if not skipping basics.")

    try:
        with open(deck_list_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'): continue
                
                parts = line.split(maxsplit=1)
                if len(parts) != 2:
                    print(f"  Warning: Skipping malformed line {line_num}: '{line}'"); missing_card_names.append(line); continue
                
                count_str, deck_card_name_original = parts
                try:
                    count = int(count_str)
                except ValueError:
                    print(f"  Warning: Invalid count line {line_num}: '{line}'"); missing_card_names.append(deck_card_name_original); continue
                if count <= 0:
                    print(f"  Warning: Non-positive count line {line_num}: '{line}'"); continue

                normalized_deck_card_name = normalize_card_name(deck_card_name_original)

                # --- Handle Basic Lands with new logic OR Skip ---
                if normalized_deck_card_name in BASIC_LAND_NAMES:
                    if skip_basic_land:
                        if debug: print(f"DEBUG: Skipping basic land due to --skip-basic-land: {count}x '{deck_card_name_original}'")
                        skipped_basic_lands_count[deck_card_name_original] = skipped_basic_lands_count.get(deck_card_name_original, 0) + count
                        continue
                    
                    # --- New Basic Land Selection Logic ---
                    if debug: print(f"DEBUG: Processing basic land: {count}x '{deck_card_name_original}' (Normalized: {normalized_deck_card_name})")
                    
                    available_basics_for_type = basic_land_details.get(normalized_deck_card_name, [])
                    if not available_basics_for_type:
                        print(f"  NOT FOUND (Basic Land): No images found for type '{deck_card_name_original}' in `basic_land_details` map.")
                        # Try fallback to general map just in case it wasn't parsed correctly but exists
                        found_path_fallback = find_image_in_map(deck_card_name_original, normalized_file_map)
                        if found_path_fallback:
                            if debug: print(f"DEBUG:   Found basic land '{deck_card_name_original}' via fallback map. Using {count} copies of '{os.path.basename(found_path_fallback)}'.")
                            images_to_print.extend([found_path_fallback] * count)
                        else:
                            missing_card_names.append(f"{count}x {deck_card_name_original} (Basic Land Type Not Found)")
                        continue

                    # Filter by set if basic_land_sets_filter is provided
                    candidate_pool = []
                    if basic_land_sets_filter:
                        for basic_info in available_basics_for_type:
                            if basic_info['set'] in basic_land_sets_filter:
                                candidate_pool.append(basic_info['path'])
                        if debug: print(f"DEBUG:   Filtered by set(s) {basic_land_sets_filter}. Candidates for '{normalized_deck_card_name}': {len(candidate_pool)}")
                        if not candidate_pool:
                            print(f"  NOT FOUND (Basic Land): No '{deck_card_name_original}' found matching sets: {basic_land_sets_filter}")
                            missing_card_names.append(f"{count}x {deck_card_name_original} (Set Mismatch: {basic_land_sets_filter})")
                            continue
                    else: # No set filter, use all available for this type
                        candidate_pool = [b['path'] for b in available_basics_for_type]
                        if debug: print(f"DEBUG:   No set filter. Candidates for '{normalized_deck_card_name}': {len(candidate_pool)}")

                    if not candidate_pool: # Should be caught above, but as a safeguard
                        print(f"  NOT FOUND (Basic Land): No candidate pool for '{deck_card_name_original}' after processing.")
                        missing_card_names.append(f"{count}x {deck_card_name_original} (No Candidates)")
                        continue
                    
                    # Now select 'count' images from candidate_pool
                    selected_paths_for_this_basic = []
                    num_unique_candidates = len(candidate_pool)

                    if count <= num_unique_candidates:
                        # Enough unique images, select 'count' without replacement
                        selected_paths_for_this_basic = random.sample(candidate_pool, count)
                        if debug: print(f"DEBUG:   Selected {count} unique basic lands for '{deck_card_name_original}' from {num_unique_candidates} candidates.")
                    else:
                        # Not enough unique images, take all unique then add duplicates
                        selected_paths_for_this_basic.extend(candidate_pool) # Add all unique ones first
                        remaining_needed = count - num_unique_candidates
                        # Randomly pick with replacement for the remainder
                        duplicates_to_add = random.choices(candidate_pool, k=remaining_needed)
                        selected_paths_for_this_basic.extend(duplicates_to_add)
                        if debug: print(f"DEBUG:   Selected all {num_unique_candidates} unique lands for '{deck_card_name_original}', plus {remaining_needed} duplicates.")
                    
                    images_to_print.extend(selected_paths_for_this_basic)
                    if debug:
                        for pth_idx, pth in enumerate(selected_paths_for_this_basic):
                            print(f"DEBUG:     -> Basic Land {pth_idx+1}: {os.path.basename(pth)}")
                    continue # End of basic land specific handling

                # --- Handle Non-Basic Lands (Original Logic) ---
                if debug: print(f"DEBUG: Attempting to find (non-basic): '{deck_card_name_original}' (Normalized: '{normalized_deck_card_name}')")
                found_path = find_image_in_map(deck_card_name_original, normalized_file_map)
                if found_path:
                    images_to_print.extend([found_path] * count)
                    if debug: print(f"DEBUG:   FOUND (non-basic): {count}x '{deck_card_name_original}' as '{os.path.basename(found_path)}'")
                else:
                    print(f"  NOT FOUND (non-basic): {count}x '{deck_card_name_original}'")
                    if debug and normalized_file_map:
                        print("DEBUG:     Available normalized keys in map:"); [print(f"DEBUG:       - '{k}'") for k in sorted(normalized_file_map.keys())]
                    elif debug: print("DEBUG:     Normalized file map is empty.")
                    missing_card_names.append(deck_card_name_original) # Original name for non-basics
    
    except FileNotFoundError:
        print(f"Error: Deck list file not found: {deck_list_path}")
        return [], []
    
    if skipped_basic_lands_count:
        print("  Skipped the following basic lands from deck list (due to --skip-basic-land):")
        for name, num in skipped_basic_lands_count.items(): print(f"    - {num}x {name}")
        
    return images_to_print, list(set(missing_card_names)) # Ensure missing_card_names are unique


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
    # Note: This validation is for MtgDeck2Print's own paper types ("letter", "legal").
    # The cameo mode will do its own validation against LAYOUTS_DATA.
    size_str = size_str.lower().strip()
    if size_str not in PAPER_SIZES_PT: # PAPER_SIZES_PT is for ReportLab
        # For cameo, we might allow other paper sizes if they are in LAYOUTS_DATA
        # However, to keep this function generic for both PDF types, we only validate against known MtgDeck2Print types.
        # The cameo function will then re-evaluate.
        # A more robust solution might be to have separate validation or expand PAPER_SIZES_PT for cameo.
        # For now, this is fine as cameo's create_pdf_cameo_style will error if 'legal' is passed.
        # if size_str.lower() in LAYOUTS_DATA["paper_layouts"]: return size_str.lower() # Potentially allow more if for cameo
        raise ValueError(f"Invalid paper type for ReportLab PDF: '{size_str}'. Supported ReportLab types: {', '.join(PAPER_SIZES_PT.keys())}. Cameo mode uses its own layout definitions.")
    return size_str

def create_pdf_grid(*args, **kwargs): # Keep signature, but logic might be elided if focusing on PNG copy
    # ... (Full ReportLab PDF generation logic as before) ...
    # This function is unchanged and used when --cameo is NOT present.
    image_files=kwargs.get("image_files")
    output_pdf_file=kwargs.get("output_pdf_file")
    paper_type_str=kwargs.get("paper_type_str")
    # ... other kwargs ...

    if not image_files: print("No image files for PDF."); return
    
    # --- ReportLab PDF Setup ---
    paper_width_pt, paper_height_pt = PAPER_SIZES_PT[paper_type_str]
    c = canvas.Canvas(output_pdf_file, pagesize=(paper_width_pt, paper_height_pt))
    
    dpi = kwargs.get("dpi", 300)
    page_margin_str = kwargs.get("page_margin_str", "5mm")
    image_spacing_pixels = kwargs.get("image_spacing_pixels", 0)
    
    page_bg_color_str = kwargs.get("page_background_color_str", "white")
    image_cell_bg_color_str = kwargs.get("image_cell_background_color_str", "black")
    
    cut_lines = kwargs.get("cut_lines", False)
    cut_line_length_str = kwargs.get("cut_line_length_str", "3mm")
    cut_line_color_str = kwargs.get("cut_line_color_str", "gray")
    cut_line_width_pt = kwargs.get("cut_line_width_pt", 0.25)

    print(f"\n--- PDF Generation Settings (ReportLab: {output_pdf_file}) ---")
    print(f"  Paper: {paper_type_str} ({paper_width_pt/inch:.2f}\" x {paper_height_pt/inch:.2f}\")")
    print(f"  DPI: {dpi}, Image Size: {TARGET_IMG_WIDTH_INCHES}\" x {TARGET_IMG_HEIGHT_INCHES}\"")
    
    try:
        page_margin_px = parse_dimension_to_pixels(page_margin_str, dpi, default_unit_is_mm=True)
    except ValueError as e:
        print(f"Error parsing page margin '{page_margin_str}': {e}. Using 0px."); page_margin_px = 0
    
    page_margin_pt = page_margin_px * (inch / dpi)
    img_spacing_pt = image_spacing_pixels * (inch / dpi)

    target_img_width_pt = TARGET_IMG_WIDTH_INCHES * inch
    target_img_height_pt = TARGET_IMG_HEIGHT_INCHES * inch
    
    grid_cols, grid_rows = (3,3) if paper_type_str == "letter" else (3,4) # MtgDeck2Print's fixed grid
    
    print(f"  Grid: {grid_cols}x{grid_rows} cards per page.")
    print(f"  Margins: {page_margin_str} ({page_margin_pt:.2f}pt), Image Spacing: {image_spacing_pixels}px ({img_spacing_pt:.2f}pt)")

    available_width_pt = paper_width_pt - 2 * page_margin_pt
    available_height_pt = paper_height_pt - 2 * page_margin_pt

    # Calculate total width/height needed by cards + spacing
    total_card_width_pt = grid_cols * target_img_width_pt + (grid_cols - 1) * img_spacing_pt
    total_card_height_pt = grid_rows * target_img_height_pt + (grid_rows - 1) * img_spacing_pt
    
    # Center the grid: Calculate starting X, Y for the top-left card's bottom-left corner
    start_x_pt = page_margin_pt + (available_width_pt - total_card_width_pt) / 2
    start_y_pt = paper_height_pt - page_margin_pt - (available_height_pt - total_card_height_pt) / 2 - target_img_height_pt # Start from top

    if total_card_width_pt > available_width_pt or total_card_height_pt > available_height_pt:
        print("  Warning: Cards + spacing might exceed available page area with current margins.")

    images_per_page = grid_cols * grid_rows
    total_images = len(image_files)
    num_pages = (total_images + images_per_page - 1) // images_per_page
    
    page_bg_color_rl = getattr(reportlab_colors, page_bg_color_str.lower(), reportlab_colors.white)
    cell_bg_color_rl = getattr(reportlab_colors, image_cell_bg_color_str.lower(), reportlab_colors.black)
    cut_line_color_rl = getattr(reportlab_colors, cut_line_color_str.lower(), reportlab_colors.gray)
    
    try:
        cut_line_len_px = parse_dimension_to_pixels(cut_line_length_str, dpi, default_unit_is_mm=True)
        cut_line_len_pt = cut_line_len_px * (inch / dpi)
    except ValueError as e:
        print(f"Error parsing cut line length '{cut_line_length_str}': {e}. Using 0px."); cut_line_len_pt = 0


    for page_num in range(num_pages):
        c.setFillColor(page_bg_color_rl)
        c.rect(0, 0, paper_width_pt, paper_height_pt, fill=1, stroke=0) # Page background

        for i in range(images_per_page):
            img_idx = page_num * images_per_page + i
            if img_idx >= total_images: break

            row = i // grid_cols
            col = i % grid_cols

            # Position for bottom-left of the image cell
            x = start_x_pt + col * (target_img_width_pt + img_spacing_pt)
            y = start_y_pt - row * (target_img_height_pt + img_spacing_pt) # y decreases as row increases

            # Draw image cell background
            c.setFillColor(cell_bg_color_rl)
            c.rect(x, y, target_img_width_pt, target_img_height_pt, fill=1, stroke=0)
            
            try:
                # drawImage handles PNG transparency against the cell background
                c.drawImage(image_files[img_idx], x, y, width=target_img_width_pt, height=target_img_height_pt, mask='auto')
            except Exception as e:
                print(f"  Warning: Could not draw image {image_files[img_idx]} on page {page_num+1}: {e}")
                c.setFillColorRGB(1, 0, 0) # Red rectangle for error
                c.rect(x, y, target_img_width_pt, target_img_height_pt, fill=1, stroke=0)
                c.setFillColorRGB(0,0,0); c.drawCentredString(x + target_img_width_pt/2, y + target_img_height_pt/2, "Error")


            if cut_lines and cut_line_len_pt > 0:
                c.setStrokeColor(cut_line_color_rl)
                c.setLineWidth(cut_line_width_pt)
                # Top edge cut lines
                c.line(x, y + target_img_height_pt, x - cut_line_len_pt, y + target_img_height_pt) # Left of top
                c.line(x + target_img_width_pt, y + target_img_height_pt, x + target_img_width_pt + cut_line_len_pt, y + target_img_height_pt) # Right of top
                # Bottom edge cut lines
                c.line(x, y, x - cut_line_len_pt, y) # Left of bottom
                c.line(x + target_img_width_pt, y, x + target_img_width_pt + cut_line_len_pt, y) # Right of bottom
                # Left edge cut lines
                c.line(x, y + target_img_height_pt, x, y + target_img_height_pt + cut_line_len_pt) # Top of left
                c.line(x, y, x, y - cut_line_len_pt) # Bottom of left
                # Right edge cut lines
                c.line(x + target_img_width_pt, y + target_img_height_pt, x + target_img_width_pt, y + target_img_height_pt + cut_line_len_pt) # Top of right
                c.line(x + target_img_width_pt, y, x + target_img_width_pt, y - cut_line_len_pt) # Bottom of right
        
        c.showPage()
    c.save()
    print(f"ReportLab PDF generation complete: {output_pdf_file} ({num_pages} page(s))")


def create_png_output(*args, **kwargs): # Keep signature
    # ... (Full PNG grid generation logic as before, unchanged) ...
    image_files=kwargs.get("image_files")
    base_output_filename=kwargs.get("base_output_filename")
    # (Assume the rest of this function is correctly implemented from previous versions)
    print(f"PNG page generation complete for base: {base_output_filename} (Not fully re-implemented in this snippet)")


def copy_deck_pngs(
    image_files_to_copy: List[str], # List of full source paths, with duplicates
    png_out_dir: str,
    debug: bool = False
):
    # ... (This function remains the same)
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
            shutil.copy2(source_path, dest_path) 
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
        formatter_class=argparse.ArgumentDefaultsHelpFormatter #type: ignore
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
    general_group.add_argument(
        "--cameo", action="store_true", 
        help="Use PIL-based PDF generation (modeled after create_pdf.py/utilities.py) when --output-format is pdf. "
             "This mode uses fixed layouts from an internal 'layouts.json' equivalent and ignores most page/layout/cut-line options. "
             "Currently best supports --paper-type letter or a4 (if in layouts). "
             "EXPECTS an 'assets' FOLDER with registration mark images (e.g., 'letter_registration.jpg') next to the script for proper Cameo output." # MODIFIED Line
    )
    general_group.add_argument(
        "--basic-land-set", type=str, default=None,
        help="Comma-separated list of set codes to filter basic lands by (e.g., 'lea,unh,neo'). "
             "If specified, only basic lands from these sets will be considered. "
             "Affects random selection of basic lands from --deck-list."
    )


    # --- Page & Layout Options (for PDF/PNG grid output, LARGELY IGNORED by --cameo) ---
    pg_layout_group = parser.add_argument_group('Page and Layout Options (for PDF/PNG grid output; largely IGNORED by --cameo mode)')
    pg_layout_group.add_argument("--paper-type", type=str, default="letter", choices=["letter", "legal"], 
                                 help="Conceptual paper type. For ReportLab PDF: Letter 3x3, Legal 3x4. For --cameo PDF: must match a layout like 'letter'.")
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

    # --- Cut Line Options (for PDF/PNG grid output, IGNORED by --cameo) ---
    cut_line_group = parser.add_argument_group('Cut Line Options (for PDF/PNG grid output; IGNORED by --cameo mode)')
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
        parser.error("--png-out_dir requires --deck-list to be specified.")
    if args.png_out_dir and (args.output_file or args.output_format != "pdf"): 
        if args.output_file:
            print("Warning: --output-file is ignored when --png-out-dir is used.")
        if args.output_format != "pdf": 
             print(f"Warning: --output-format {args.output_format} is ignored when --png-out-dir is used.")
    
    if args.cameo and args.output_format != "pdf":
        print("Warning: --cameo option is only applicable when --output-format is 'pdf'. Ignoring --cameo.")
        args.cameo = False # Effectively disable it if not PDF

    # --- Initial Validations (Common) ---
    if not os.path.isdir(args.png_dir): print(f"Error: PNG directory '{args.png_dir}' not found."); return
    if args.deck_list and not os.path.isfile(args.deck_list):
        print(f"Error: Deck list file '{args.deck_list}' not found."); return
    
    validated_paper_type: str
    try: 
        # parse_paper_type validates against MtgDeck2Print's known types ("letter", "legal")
        # The cameo function will do further validation against its own layouts.
        validated_paper_type = parse_paper_type(args.paper_type) 
    except ValueError as e: print(f"Error: {e}"); return

    # --- Parse basic_land_sets_filter ---
    parsed_basic_land_sets: Optional[List[str]] = None
    if args.basic_land_set:
        parsed_basic_land_sets = [s.strip().lower() for s in args.basic_land_set.split(',') if s.strip()]
        if args.debug and parsed_basic_land_sets:
            print(f"DEBUG: Parsed basic land set filter: {parsed_basic_land_sets}")

    # --- Determine list of images to process ---
    image_files_to_process: List[str] = [] 
    missing_cards_from_deck: List[str] = []

    if args.deck_list:
        print("--- Deck List Mode ---")
        image_files_to_process, missing_cards_from_deck = process_deck_list(
            args.deck_list, args.png_dir, args.skip_basic_land, parsed_basic_land_sets, args.debug
        ) 
        if missing_cards_from_deck: 
            write_missing_cards_file(args.deck_list, missing_cards_from_deck) 
        
        if not image_files_to_process and not args.png_out_dir: 
            print("No images to print (after potential skips). Exiting.")
            return
        if image_files_to_process : 
            print(f"Prepared {len(image_files_to_process)} image instances (excluding any skipped basic lands).")

    elif not args.png_out_dir: 
        print("--- Directory Scan Mode (for PDF/PNG grid) ---")
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
        print("Error: --png-out-dir specified without a --deck-list. Nothing to do.")
        return


    # --- Perform Action: Copy PNGs or Generate Grid ---
    if args.png_out_dir:
        if not args.deck_list: 
            print("Critical Error: --png-out-dir mode reached without a deck list. Please report this bug.")
            return
        if image_files_to_process: 
             copy_deck_pngs(image_files_to_process, args.png_out_dir, args.debug)
        elif not missing_cards_from_deck: 
             print("No images to copy (deck list may have contained only skipped basic lands or was empty).")

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

        name_for_pdf_label = os.path.basename(base_output_filename_final) # Get just the filename part for the label

        if args.output_format == "pdf":
            output_pdf_with_ext = f"{base_output_filename_final}.pdf"
            
            if args.cameo:
                # Warn about ignored arguments if --cameo is active
                ignored_args_for_cameo = []
                layout_actions_to_check = [
                    action for action in pg_layout_group._group_actions 
                    if action.dest != "image_cell_bg_color" # EXCLUDE this one
                ]
                defaults = {arg.dest: arg.default for arg in pg_layout_group._group_actions + cut_line_group._group_actions} # type: ignore
                if args.page_margin != defaults["page_margin"]: ignored_args_for_cameo.append("--page-margin")
                if args.image_spacing_pixels != defaults["image_spacing_pixels"]: ignored_args_for_cameo.append("--image-spacing-pixels")
                if args.page_bg_color != defaults["page_bg_color"]: ignored_args_for_cameo.append("--page-bg-color")
                if args.cut_lines: ignored_args_for_cameo.append("--cut-lines") # Default is False
                if args.cut_line_length != defaults["cut_line_length"]: ignored_args_for_cameo.append("--cut-line-length")
                if args.cut_line_color != defaults["cut_line_color"]: ignored_args_for_cameo.append("--cut-line-color")
                if args.cut_line_width_pt != defaults["cut_line_width_pt"]: ignored_args_for_cameo.append("--cut-line-width-pt")
                
                if ignored_args_for_cameo:
                    print(f"Warning: --cameo mode is active. The following options are ignored as layout is dictated by internal cameo profiles: {', '.join(ignored_args_for_cameo)}")
                
                create_pdf_cameo_style(
                    image_files=image_files_to_process,
                    output_pdf_file=output_pdf_with_ext,
                    paper_type_arg=validated_paper_type, # This is MtgDeck2Print's "letter" or "legal"
                    target_dpi=args.dpi,
                    image_cell_bg_color_str=args.image_cell_bg_color,
                    pdf_name_label=name_for_pdf_label,
                    debug=args.debug
                )
            else: # Original ReportLab PDF
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
            print(f"Error: Unknown output format '{args.output_format}'.") # Should be caught by argparse choices

from typing import Any # Add Any for LAYOUTS_DATA type hint if not already there

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import os
import glob
import argparse
import unicodedata
import re
import shutil
from typing import List, Tuple, Dict, Optional, Set, Union, Any
from collections import defaultdict
import math
import random
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, quote

from PIL import Image, ImageDraw, ImageFont
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

# Global temp file tracking for cleanup
_temp_files: Set[str] = set()

# --- Web Server Functions ---
def list_webdav_directory(base_url: str, path: str = "/", debug: bool = False) -> List[Dict[str, str]]:
    """
    List files in a WebDAV directory using PROPFIND.
    Returns a list of dicts with 'name' and 'href' (as a full URL) keys.
    """
    url = urljoin(base_url, path)
    if debug:
        print(f"DEBUG: Listing WebDAV directory: {url}")
    
    # Build PROPFIND request
    propfind_body = '''<?xml version="1.0" encoding="utf-8"?>
    <D:propfind xmlns:D="DAV:">
        <D:prop>
            <D:displayname/>
            <D:resourcetype/>
        </D:prop>
    </D:propfind>'''
    
    req = urllib.request.Request(
        url,
        data=propfind_body.encode('utf-8'),
        headers={
            'Content-Type': 'application/xml; charset=utf-8',
            'Depth': '1'
        },
        method='PROPFIND'
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read().decode('utf-8')
            
        # Parse XML response
        root = ET.fromstring(content)
        files = []
        
        # Define namespace
        ns = {'d': 'DAV:'}
        
        for response_elem in root.findall('.//d:response', ns):
            href_elem = response_elem.find('d:href', ns)
            displayname_elem = response_elem.find('.//d:displayname', ns)
            resourcetype_elem = response_elem.find('.//d:resourcetype', ns)
            
            if href_elem is not None:
                relative_href = href_elem.text
                # Skip directories (they have a <collection/> element)
                if resourcetype_elem is not None and resourcetype_elem.find('d:collection', ns) is not None:
                    continue
                    
                # Get filename
                if displayname_elem is not None and displayname_elem.text:
                    filename = displayname_elem.text
                else:
                    # Extract filename from href
                    filename = os.path.basename(urllib.parse.unquote(relative_href.rstrip('/')))
                
                if filename and filename.lower().endswith('.png'):
                    # --- FIX: Construct the full URL here ---
                    # The href from WebDAV is typically root-relative (e.g., /path/to/file.png)
                    # urljoin handles this correctly.
                    full_url = urljoin(base_url, relative_href)
                    files.append({
                        'name': filename,
                        'href': full_url  # Store the full URL
                    })
        
        if debug:
            print(f"DEBUG: Found {len(files)} PNG files in WebDAV directory")
        
        return files
        
    except urllib.error.HTTPError as e:
        if e.code == 405:  # Method not allowed - try simple directory listing
            return list_http_directory(url, debug)
        else:
            print(f"Error listing WebDAV directory: HTTP {e.code} - {e.reason}")
            return []
    except Exception as e:
        print(f"Error listing WebDAV directory: {e}")
        return []

def list_http_directory(url: str, debug: bool = False) -> List[Dict[str, str]]:
    """
    Fallback method to list files from a simple HTTP directory listing.
    Parses HTML for links to PNG files. Returns full URLs.
    """

    # --- FIX: Ensure the URL is treated as a directory for urljoin ---
    if not url.endswith('/'):
        url += '/'

    if debug:
        print(f"DEBUG: Attempting HTTP directory listing: {url}")
    
    try:
        with urllib.request.urlopen(url) as response:
            content = response.read().decode('utf-8')
        
        # Simple regex to find links to PNG files
        png_pattern = r'href="([^"]+\.png)"'
        matches = re.findall(png_pattern, content, re.IGNORECASE)
        
        files = []
        for match in matches:
            filename = os.path.basename(urllib.parse.unquote(match))
            # --- FIX: Construct the full URL here ---
            # The 'match' can be a relative path (e.g., "card.png").
            # urljoin correctly combines the directory URL with the relative path.
            full_url = urljoin(url, match)
            files.append({
                'name': filename,
                'href': full_url # Store the full URL
            })
        
        if debug:
            print(f"DEBUG: Found {len(files)} PNG files in HTTP directory listing")
        
        return files
        
    except Exception as e:
        print(f"Error listing HTTP directory: {e}")
        return []

def download_image(url: str, dest_path: Optional[str] = None, debug: bool = False) -> Optional[str]:
    """
    Download an image from URL. If dest_path is None, saves to a temp file.
    Returns the path to the downloaded file, or None on error.
    """
    if debug:
        print(f"DEBUG: Downloading image from {url}")
    
    try:
        # Create temp file if no destination specified
        if dest_path is None:
            fd, dest_path = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            _temp_files.add(dest_path)
        
        # Download the file
        urllib.request.urlretrieve(url, dest_path)
        
        if debug:
            print(f"DEBUG: Downloaded to {dest_path}")
        
        return dest_path
        
    except Exception as e:
        print(f"Error downloading image from {url}: {e}")
        if dest_path and os.path.exists(dest_path):
            os.remove(dest_path)
            _temp_files.discard(dest_path)
        return None

class ImageSource:
    """Wrapper class to handle both local files and web URLs uniformly"""
    def __init__(self, path_or_url: str, is_url: bool = False):
        self.original = path_or_url
        self.is_url = is_url
        self.local_path = None if is_url else path_or_url
        self.temp_file = None
    
    def get_local_path(self, debug: bool = False) -> Optional[str]:
        """Get a local file path, downloading if necessary"""
        if not self.is_url:
            return self.local_path
        
        if self.temp_file is None:
            self.temp_file = download_image(self.original, debug=debug)
        
        return self.temp_file
    
    def cleanup(self):
        """Clean up any temporary files"""
        if self.temp_file and os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
                _temp_files.discard(self.temp_file)
            except:
                pass
            self.temp_file = None
    
    def __del__(self):
        self.cleanup()

# --- Modified PNG discovery function ---
def discover_images(
    png_dir: Optional[str] = None,
    image_server_base_url: Optional[str] = None,
    image_server_path_prefix: str = "/webdav_images",
    skip_basic_land: bool = False,
    basic_land_sets_filter: Optional[List[str]] = None,
    debug: bool = False
) -> Tuple[Dict[str, ImageSource], Dict[str, List[Dict[str, Any]]]]:
    """
    Discover images from local directory or web server.
    Returns (normalized_file_map, basic_land_details)
    """
    normalized_file_map: Dict[str, ImageSource] = {}
    basic_land_details: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    if image_server_base_url:
        # Web server mode
        if debug:
            print(f"DEBUG: Discovering images from web server: {image_server_base_url}")
            print(f"DEBUG: Path prefix: {image_server_path_prefix}")
        
        # List files from web server
        files = list_webdav_directory(image_server_base_url, image_server_path_prefix, debug)
        
        # --- FIX: Simplified loop ---
        for file_info in files:
            filename = file_info['name']
            # The 'href' from file_info is now a complete, absolute URL.
            file_url = file_info['href']
            
            basename_no_ext = os.path.splitext(filename)[0]
            
            # Create ImageSource wrapper
            img_source = ImageSource(file_url, is_url=True)
            
            # Attempt to parse as basic land
            parsed_basic = parse_basic_land_filename(basename_no_ext)
            if parsed_basic:
                land_type, set_code, unique_id = parsed_basic
                basic_land_details[land_type].append({
                    'set': set_code,
                    'source': img_source,
                    'id': unique_id
                })
                if debug:
                    print(f"DEBUG:   Basic Land Parsed: '{basename_no_ext}' -> Type: {land_type}, Set: {set_code}, URL: {file_url}")
            
            # Always add to normalized map
            normalized_filename_key = normalize_card_name(basename_no_ext)
            if normalized_filename_key not in normalized_file_map:
                normalized_file_map[normalized_filename_key] = img_source
            elif debug:
                print(f"DEBUG:     WARNING: Normalized key '{normalized_filename_key}' from '{filename}' conflicts. Using first found.")
    
    elif png_dir:
        # Local directory mode (original behavior)
        if debug:
            print(f"DEBUG: Scanning PNG directory '{png_dir}' for PNGs...")
        
        for ext in ("*.png", "*.PNG"):
            for filepath in glob.glob(os.path.join(png_dir, ext)):
                basename_no_ext = os.path.splitext(os.path.basename(filepath))[0]
                
                # Create ImageSource wrapper for local file
                img_source = ImageSource(filepath, is_url=False)
                
                # Attempt to parse as basic land
                parsed_basic = parse_basic_land_filename(basename_no_ext)
                if parsed_basic:
                    land_type, set_code, unique_id = parsed_basic
                    basic_land_details[land_type].append({
                        'set': set_code,
                        'source': img_source,
                        'id': unique_id
                    })
                    if debug:
                        print(f"DEBUG:   Basic Land Parsed: '{basename_no_ext}' -> Type: {land_type}, Set: {set_code}, Path: {filepath}")
                
                # Always add to normalized map
                normalized_filename_key = normalize_card_name(basename_no_ext)
                if normalized_filename_key not in normalized_file_map:
                    normalized_file_map[normalized_filename_key] = img_source
                elif debug:
                    print(f"DEBUG:     WARNING: Normalized key '{normalized_filename_key}' from '{os.path.basename(filepath)}' conflicts. Using first found.")
    
    return normalized_file_map, basic_land_details

# --- START: Cameo PDF Generation Code (Adapted from utilities.py and layouts.json) ---

# Embedded layouts.json content
LAYOUTS_DATA: Dict[str, Any] = {
    "paper_layouts": {
        "letter": {
            "width": 3300,
            "height": 2550,
            "card_layouts": {
                "standard": {
                    "width": 742,
                    "height": 1036,
                    "x_pos": [141, 900, 1658, 2417],
                    "y_pos": [232, 1282],
                    "template": "letter_standard_v3"
                },
                "japanese": {
                    "width": 694, "height": 1015,
                    "x_pos": [165, 924, 1682, 2441], "y_pos": [243, 1293],
                    "template": "letter_japanese_v1"
                },
            }
        },
        "a4": {
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

class CameoPaperSize:
    LETTER = "letter"
    A4 = "a4"

class CameoCardSize:
    STANDARD = "standard"
    JAPANESE = "japanese"

def parse_basic_land_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    """
    Parses a basic land filename like 'Forest-avr-242.png' or 'Island-ZEN-123b.png'.
    Returns (land_type, set_code, unique_part) or None if not a match.
    """
    basename_no_ext = os.path.splitext(os.path.basename(filename))[0]
    parts = basename_no_ext.split('-')
    
    if len(parts) >= 3:
        land_type_candidate = parts[0].lower()
        if land_type_candidate in BASIC_LAND_NAMES:
            set_code = parts[1].lower()
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

def draw_card_with_border_cameo(
    card_image: Image.Image,
    base_image: Image.Image,
    box: tuple[int, int, int, int],
    print_bleed: int,
    cell_bg_color_pil: Union[str, Tuple[int, int, int], None]
):
    origin_x, origin_y, origin_width, origin_height = box

    if cell_bg_color_pil is not None:
        draw = ImageDraw.Draw(base_image)
        
        if print_bleed > 0:
            max_offset = print_bleed - 1 if print_bleed > 0 else 0
            cell_rect_x0 = origin_x - max_offset
            cell_rect_y0 = origin_y - max_offset
            cell_rect_x1 = origin_x + origin_width + max_offset
            cell_rect_y1 = origin_y + origin_height + max_offset
        else:
            cell_rect_x0 = origin_x
            cell_rect_y0 = origin_y
            cell_rect_x1 = origin_x + origin_width
            cell_rect_y1 = origin_y + origin_height

        draw.rectangle(
            [cell_rect_x0, cell_rect_y0, cell_rect_x1, cell_rect_y1],
            fill=cell_bg_color_pil
        )

    for i in reversed(range(print_bleed)):
        card_image_resized_for_this_iteration = card_image.resize(
            (origin_width + (2 * i), origin_height + (2 * i))
        )
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
    cell_bg_color_pil: Union[str, Tuple[int, int, int], None]
):
    num_slots_on_page = num_rows * num_cols

    for i, original_card_pil_image in enumerate(card_images):
        if i >= num_slots_on_page: break
        current_card_image = original_card_pil_image
        slot_x_on_page_scaled = math.floor(x_pos_layout[i % num_cols] * ppi_ratio)
        slot_y_on_page_scaled = math.floor(y_pos_layout[i // num_cols] * ppi_ratio)
        
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

        paste_box_for_card_content = (
            slot_x_on_page_scaled + extend_corners_page_px_scaled,
            slot_y_on_page_scaled + extend_corners_page_px_scaled,
            card_render_width_scaled,
            card_render_height_scaled
        )

        final_print_bleed_iterations = math.ceil(print_bleed_layout_units * ppi_ratio) + extend_corners_page_px_scaled
        
        draw_card_with_border_cameo(
            current_card_image,
            base_image,
            paste_box_for_card_content,
            final_print_bleed_iterations,
            cell_bg_color_pil
        )

def create_pdf_cameo_style(
    image_sources: List[ImageSource],  # Changed from image_files to image_sources
    output_pdf_file: str,
    paper_type_arg: str,
    target_dpi: int,
    image_cell_bg_color_str: str,
    pdf_name_label: Optional[str],
    debug: bool = False
):
    print(f"\n--- Cameo PDF Generation (PIL-based) ---")
    print(f"Output file: {output_pdf_file}")
    
    default_cell_bg_color = "black"
    if image_cell_bg_color_str.lower() != default_cell_bg_color:
        print(f"  Image Cell Background Color: {image_cell_bg_color_str}")

    cameo_paper_key: str
    if paper_type_arg.lower() == "letter":
        cameo_paper_key = CameoPaperSize.LETTER
    elif paper_type_arg.lower() == "a4":
        cameo_paper_key = CameoPaperSize.A4
    else:
        print(f"Error: --cameo PDF generation: Paper type '{paper_type_arg}' is not directly supported by embedded cameo layouts.")
        return
    
    cameo_card_key = CameoCardSize.STANDARD

    try:
        paper_layout_config = LAYOUTS_DATA["paper_layouts"][cameo_paper_key]
        card_layout_config = paper_layout_config["card_layouts"][cameo_card_key]
    except KeyError:
        print(f"Error: Layout for paper '{cameo_paper_key}' and card size '{cameo_card_key}' not found.")
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
        print(f"DEBUG CAMEO: Grid: {num_cols}x{num_rows} ({num_cards_per_page} cards/page)")

    # Load registration mark
    script_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir_cameo = os.path.join(script_dir, "assets")
    registration_filename = f'{cameo_paper_key}_registration.jpg'
    registration_path = os.path.join(asset_dir_cameo, registration_filename)
    
    master_page_background: Optional[Image.Image] = None
    if os.path.exists(registration_path):
        try:
            reg_im_original = Image.open(registration_path)
            reg_im_scaled = reg_im_original.resize((page_width_px_scaled, page_height_px_scaled))
            if reg_im_scaled.mode != 'RGB':
                reg_im_scaled = reg_im_scaled.convert('RGB')
            master_page_background = reg_im_scaled
            if debug: print(f"DEBUG CAMEO: Loaded registration mark: {registration_path}")
        except Exception as e_reg:
            print(f"  Warning: Could not load registration image: {e_reg}")

    if master_page_background is None:
        master_page_background = Image.new("RGB", (page_width_px_scaled, page_height_px_scaled), "white")

    pil_cell_bg_color: Union[str, Tuple[int,int,int], None] = image_cell_bg_color_str
    
    all_pil_pages: List[Image.Image] = []
    total_images_to_process = len(image_sources)

    for page_start_index in range(0, total_images_to_process, num_cards_per_page):
        current_page_pil_image = master_page_background.copy()

        image_sources_for_this_page = image_sources[page_start_index : page_start_index + num_cards_per_page]
        pil_card_images_for_page: List[Image.Image] = []
        
        for img_source in image_sources_for_this_page:
            try:
                # Get local path (downloads if needed)
                local_path = img_source.get_local_path(debug)
                if local_path:
                    img = Image.open(local_path)
                    img = img.convert('RGBA')
                    pil_card_images_for_page.append(img)
                else:
                    raise Exception("Failed to get local path")
            except Exception as e:
                print(f"  Warning: Could not process image '{img_source.original}': {e}")
                placeholder_w = int(TARGET_IMG_WIDTH_INCHES * target_dpi)
                placeholder_h = int(TARGET_IMG_HEIGHT_INCHES * target_dpi)
                placeholder = Image.new("RGBA", (placeholder_w, placeholder_h), (255, 192, 203, 255))
                draw_placeholder = ImageDraw.Draw(placeholder)
                try:
                    font_placeholder = ImageFont.load_default()
                    draw_placeholder.text((5,5), "Error\nLoading", fill="black", font=font_placeholder)
                except:
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
            cell_bg_color_pil=pil_cell_bg_color
        )
        
        page_num_for_label = (page_start_index // num_cards_per_page) + 1
        template_name = card_layout_config.get("template", "unknown_template")
        
        base_label_part = f"template: {template_name}, sheet: {page_num_for_label}"
        if pdf_name_label:
            label_text = f"name: {pdf_name_label}, {base_label_part}"
        else:
            label_text = base_label_part

        try:
            draw_page_text = ImageDraw.Draw(current_page_pil_image)
            text_x_pos = math.floor((paper_layout_config["width"] - 180) * ppi_ratio)
            text_y_pos = math.floor((paper_layout_config["height"] - 180) * ppi_ratio)
            font_size_scaled = math.floor(40 * ppi_ratio)
            
            try:
                page_font = ImageFont.load_default(size=font_size_scaled)
            except:
                page_font = ImageFont.load_default()
            
            draw_page_text.text((text_x_pos, text_y_pos), label_text, fill=(0,0,0), anchor="ra", font=page_font)
        except Exception as e_font:
            if debug: print(f"DEBUG CAMEO: Could not draw page label: {e_font}")

        all_pil_pages.append(current_page_pil_image)

    if not all_pil_pages:
        print("Cameo PDF: No pages generated.")
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
    normalized_file_map: Dict[str, ImageSource]  # Changed to ImageSource
) -> Optional[ImageSource]:
    normalized_deck_card_name = normalize_card_name(deck_card_name_original)
    if normalized_deck_card_name in normalized_file_map:
        return normalized_file_map[normalized_deck_card_name]
    return None

def process_deck_list(
    deck_list_path: str,
    normalized_file_map: Dict[str, ImageSource],  # Changed to ImageSource
    basic_land_details: Dict[str, List[Dict[str, Any]]],  # Changed to include ImageSource
    skip_basic_land: bool,
    basic_land_sets_filter: Optional[List[str]],
    debug: bool = False
) -> Tuple[List[ImageSource], List[str]]:  # Changed return type
    images_to_print: List[ImageSource] = []
    missing_card_names: List[str] = []
    skipped_basic_lands_count: Dict[str, int] = {}

    if debug:
        print(f"DEBUG: Processing deck list from '{deck_list_path}'")
        if basic_land_sets_filter:
            print(f"DEBUG: Basic land set filter active: {basic_land_sets_filter}")

    if not normalized_file_map and not basic_land_details and not skip_basic_land:
        print(f"  No images found in source. Cannot process deck list if not skipping basics.")

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
                except ValueError:
                    print(f"  Warning: Invalid count line {line_num}: '{line}'")
                    missing_card_names.append(deck_card_name_original)
                    continue
                if count <= 0:
                    print(f"  Warning: Non-positive count line {line_num}: '{line}'")
                    continue

                normalized_deck_card_name = normalize_card_name(deck_card_name_original)

                # Handle Basic Lands
                if normalized_deck_card_name in BASIC_LAND_NAMES:
                    if skip_basic_land:
                        if debug: print(f"DEBUG: Skipping basic land: {count}x '{deck_card_name_original}'")
                        skipped_basic_lands_count[deck_card_name_original] = skipped_basic_lands_count.get(deck_card_name_original, 0) + count
                        continue
                    
                    if debug: print(f"DEBUG: Processing basic land: {count}x '{deck_card_name_original}'")
                    
                    available_basics_for_type = basic_land_details.get(normalized_deck_card_name, [])
                    if not available_basics_for_type:
                        print(f"  NOT FOUND (Basic Land): No images for type '{deck_card_name_original}'")
                        # Try fallback to general map
                        found_source_fallback = find_image_in_map(deck_card_name_original, normalized_file_map)
                        if found_source_fallback:
                            if debug: print(f"DEBUG:   Found basic land via fallback map")
                            images_to_print.extend([found_source_fallback] * count)
                        else:
                            missing_card_names.append(f"{count}x {deck_card_name_original} (Basic Land Type Not Found)")
                        continue

                    # Filter by set if needed
                    candidate_pool = []
                    if basic_land_sets_filter:
                        for basic_info in available_basics_for_type:
                            if basic_info['set'] in basic_land_sets_filter:
                                candidate_pool.append(basic_info['source'])
                        if debug: print(f"DEBUG:   Filtered by set(s) {basic_land_sets_filter}. Candidates: {len(candidate_pool)}")
                        if not candidate_pool:
                            print(f"  NOT FOUND (Basic Land): No '{deck_card_name_original}' matching sets: {basic_land_sets_filter}")
                            missing_card_names.append(f"{count}x {deck_card_name_original} (Set Mismatch: {basic_land_sets_filter})")
                            continue
                    else:
                        candidate_pool = [b['source'] for b in available_basics_for_type]
                        if debug: print(f"DEBUG:   No set filter. Candidates: {len(candidate_pool)}")

                    # Select 'count' images from candidate_pool
                    selected_sources_for_this_basic = []
                    num_unique_candidates = len(candidate_pool)

                    if count <= num_unique_candidates:
                        selected_sources_for_this_basic = random.sample(candidate_pool, count)
                        if debug: print(f"DEBUG:   Selected {count} unique basic lands")
                    else:
                        selected_sources_for_this_basic.extend(candidate_pool)
                        remaining_needed = count - num_unique_candidates
                        duplicates_to_add = random.choices(candidate_pool, k=remaining_needed)
                        selected_sources_for_this_basic.extend(duplicates_to_add)
                        if debug: print(f"DEBUG:   Selected all {num_unique_candidates} unique + {remaining_needed} duplicates")
                    
                    images_to_print.extend(selected_sources_for_this_basic)
                    continue

                # Handle Non-Basic Lands
                if debug: print(f"DEBUG: Finding non-basic: '{deck_card_name_original}'")
                found_source = find_image_in_map(deck_card_name_original, normalized_file_map)
                if found_source:
                    images_to_print.extend([found_source] * count)
                    if debug: print(f"DEBUG:   FOUND: {count}x '{deck_card_name_original}'")
                else:
                    print(f"  NOT FOUND: {count}x '{deck_card_name_original}'")
                    missing_card_names.append(deck_card_name_original)
    
    except FileNotFoundError:
        print(f"Error: Deck list file not found: {deck_list_path}")
        return [], []
    
    if skipped_basic_lands_count:
        print("  Skipped the following basic lands:")
        for name, num in skipped_basic_lands_count.items():
            print(f"    - {num}x {name}")
        
    return images_to_print, list(set(missing_card_names))

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

def parse_dimension_to_pixels(dim_str: str, dpi: int, default_unit_is_mm: bool = False) -> int:
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
    size_str = size_str.lower().strip()
    if size_str not in PAPER_SIZES_PT:
        raise ValueError(f"Invalid paper type: '{size_str}'. Supported: {', '.join(PAPER_SIZES_PT.keys())}")
    return size_str

def create_pdf_grid(image_sources: List[ImageSource], **kwargs):  # Changed to ImageSource
    output_pdf_file = kwargs.get("output_pdf_file")
    paper_type_str = kwargs.get("paper_type_str")
    
    if not image_sources:
        print("No images for PDF.")
        return
    
    # Download all images first if needed
    local_paths = []
    for img_source in image_sources:
        local_path = img_source.get_local_path(kwargs.get("debug", False))
        if local_path:
            local_paths.append(local_path)
        else:
            print(f"Warning: Could not get image from {img_source.original}")
            # Add placeholder path
            local_paths.append(None)
    
    # ReportLab PDF Setup
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
        print(f"Error parsing page margin '{page_margin_str}': {e}. Using 0px.")
        page_margin_px = 0
    
    page_margin_pt = page_margin_px * (inch / dpi)
    img_spacing_pt = image_spacing_pixels * (inch / dpi)

    target_img_width_pt = TARGET_IMG_WIDTH_INCHES * inch
    target_img_height_pt = TARGET_IMG_HEIGHT_INCHES * inch
    
    grid_cols, grid_rows = (3,3) if paper_type_str == "letter" else (3,4)
    
    print(f"  Grid: {grid_cols}x{grid_rows} cards per page.")
    print(f"  Margins: {page_margin_str} ({page_margin_pt:.2f}pt), Spacing: {image_spacing_pixels}px ({img_spacing_pt:.2f}pt)")

    available_width_pt = paper_width_pt - 2 * page_margin_pt
    available_height_pt = paper_height_pt - 2 * page_margin_pt

    total_card_width_pt = grid_cols * target_img_width_pt + (grid_cols - 1) * img_spacing_pt
    total_card_height_pt = grid_rows * target_img_height_pt + (grid_rows - 1) * img_spacing_pt
    
    start_x_pt = page_margin_pt + (available_width_pt - total_card_width_pt) / 2
    start_y_pt = paper_height_pt - page_margin_pt - (available_height_pt - total_card_height_pt) / 2 - target_img_height_pt

    if total_card_width_pt > available_width_pt or total_card_height_pt > available_height_pt:
        print("  Warning: Cards + spacing might exceed available page area.")

    images_per_page = grid_cols * grid_rows
    total_images = len(local_paths)
    num_pages = (total_images + images_per_page - 1) // images_per_page
    
    page_bg_color_rl = getattr(reportlab_colors, page_bg_color_str.lower(), reportlab_colors.white)
    cell_bg_color_rl = getattr(reportlab_colors, image_cell_bg_color_str.lower(), reportlab_colors.black)
    cut_line_color_rl = getattr(reportlab_colors, cut_line_color_str.lower(), reportlab_colors.gray)
    
    try:
        cut_line_len_px = parse_dimension_to_pixels(cut_line_length_str, dpi, default_unit_is_mm=True)
        cut_line_len_pt = cut_line_len_px * (inch / dpi)
    except ValueError as e:
        print(f"Error parsing cut line length '{cut_line_length_str}': {e}. Using 0px.")
        cut_line_len_pt = 0

    for page_num in range(num_pages):
        c.setFillColor(page_bg_color_rl)
        c.rect(0, 0, paper_width_pt, paper_height_pt, fill=1, stroke=0)

        for i in range(images_per_page):
            img_idx = page_num * images_per_page + i
            if img_idx >= total_images: break

            row = i // grid_cols
            col = i % grid_cols

            x = start_x_pt + col * (target_img_width_pt + img_spacing_pt)
            y = start_y_pt - row * (target_img_height_pt + img_spacing_pt)

            # Draw cell background
            c.setFillColor(cell_bg_color_rl)
            c.rect(x, y, target_img_width_pt, target_img_height_pt, fill=1, stroke=0)
            
            if local_paths[img_idx]:
                try:
                    c.drawImage(local_paths[img_idx], x, y, width=target_img_width_pt, height=target_img_height_pt, mask='auto')
                except Exception as e:
                    print(f"  Warning: Could not draw image {img_idx} on page {page_num+1}: {e}")
                    c.setFillColorRGB(1, 0, 0)
                    c.rect(x, y, target_img_width_pt, target_img_height_pt, fill=1, stroke=0)
                    c.setFillColorRGB(0,0,0)
                    c.drawCentredString(x + target_img_width_pt/2, y + target_img_height_pt/2, "Error")

            if cut_lines and cut_line_len_pt > 0:
                c.setStrokeColor(cut_line_color_rl)
                c.setLineWidth(cut_line_width_pt)
                # Draw cut lines
                c.line(x, y + target_img_height_pt, x - cut_line_len_pt, y + target_img_height_pt)
                c.line(x + target_img_width_pt, y + target_img_height_pt, x + target_img_width_pt + cut_line_len_pt, y + target_img_height_pt)
                c.line(x, y, x - cut_line_len_pt, y)
                c.line(x + target_img_width_pt, y, x + target_img_width_pt + cut_line_len_pt, y)
                c.line(x, y + target_img_height_pt, x, y + target_img_height_pt + cut_line_len_pt)
                c.line(x, y, x, y - cut_line_len_pt)
                c.line(x + target_img_width_pt, y + target_img_height_pt, x + target_img_width_pt, y + target_img_height_pt + cut_line_len_pt)
                c.line(x + target_img_width_pt, y, x + target_img_width_pt, y - cut_line_len_pt)
        
        c.showPage()
    c.save()
    print(f"ReportLab PDF generation complete: {output_pdf_file} ({num_pages} page(s))")

def create_png_output(*args, **kwargs):
    # This would need similar modifications to handle ImageSource
    print(f"PNG page generation not fully implemented for web server mode")

def copy_deck_pngs(
    image_sources: List[ImageSource],  # Changed from image_files to image_sources
    png_out_dir: str,
    debug: bool = False
):
    if not image_sources:
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

    for img_source in image_sources:
        # Get local path (downloads if needed)
        local_path = img_source.get_local_path(debug)
        if not local_path:
            print(f"Warning: Could not get image from {img_source.original}")
            continue

        # Extract filename from original source
        if img_source.is_url:
            original_basename = os.path.basename(urllib.parse.unquote(img_source.original))
        else:
            original_basename = os.path.basename(img_source.original)
        
        base, ext = os.path.splitext(original_basename)

        source_key = img_source.original
        source_file_copy_counts[source_key] += 1
        current_copy_num = source_file_copy_counts[source_key]

        if current_copy_num == 1:
            dest_basename = original_basename
        else:
            dest_basename = f"{base}-{current_copy_num}{ext}"
        
        dest_path = os.path.join(png_out_dir, dest_basename)

        try:
            shutil.copy2(local_path, dest_path)
            if debug:
                print(f"DEBUG: Copied to '{dest_path}'")
            copied_count += 1
        except Exception as e:
            print(f"Error copying to '{dest_path}': {e}")
            
    print(f"Successfully copied {copied_count} PNG files to '{png_out_dir}'.")

def cleanup_temp_files():
    """Clean up any temporary files created during execution"""
    global _temp_files
    for temp_file in _temp_files:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
    _temp_files.clear()

# --- Main Function ---
def main():
    parser = argparse.ArgumentParser(
        description="Lay out PNG images or copy them based on a deck list.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter #type: ignore
    )
    # --- Input/Output Control ---
    mode_group = parser.add_argument_group('Primary Operation Modes (choose one output type)')
    mode_group.add_argument("--png-dir", type=str, help="Directory containing source PNG files.")
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
    
    # --- Web Server Options ---
    webserver_group = parser.add_argument_group('Image Server Options (Nginx WebDAV)')
    webserver_group.add_argument(
        "--image-server-base-url", type=str, default=None,
        help="Base URL of the Nginx WebDAV image server (e.g., http://localhost:8088). "
             "If provided, images will be fetched from this server instead of --png-dir."
    )
    webserver_group.add_argument(
        "--image-server-path-prefix", type=str, default="/webdav_images",
        help="Base path prefix on image server."
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
             "EXPECTS an 'assets' FOLDER with registration mark images (e.g., 'letter_registration.jpg') next to the script for proper Cameo output."
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
    if not args.png_dir and not args.image_server_base_url:
        parser.error("Either --png-dir or --image-server-base-url must be specified.")
    
    if args.png_dir and args.image_server_base_url:
        parser.error("Cannot specify both --png-dir and --image-server-base-url. Choose one source.")
    
    if args.png_out_dir and not args.deck_list:
        parser.error("--png-out-dir requires --deck-list to be specified.")
    if args.png_out_dir and (args.output_file or args.output_format != "pdf"): 
        if args.output_file:
            print("Warning: --output-file is ignored when --png-out-dir is used.")
        if args.output_format != "pdf": 
             print(f"Warning: --output-format {args.output_format} is ignored when --png-out-dir is used.")
    
    if args.cameo and args.output_format != "pdf":
        print("Warning: --cameo option is only applicable when --output-format is 'pdf'. Ignoring --cameo.")
        args.cameo = False

    # --- Initial Validations ---
    if args.png_dir and not os.path.isdir(args.png_dir):
        print(f"Error: PNG directory '{args.png_dir}' not found."); return
    if args.deck_list and not os.path.isfile(args.deck_list):
        print(f"Error: Deck list file '{args.deck_list}' not found."); return
    
    validated_paper_type: str
    try:
        validated_paper_type = parse_paper_type(args.paper_type)
    except ValueError as e: print(f"Error: {e}"); return

    # --- Parse basic_land_sets_filter ---
    parsed_basic_land_sets: Optional[List[str]] = None
    if args.basic_land_set:
        parsed_basic_land_sets = [s.strip().lower() for s in args.basic_land_set.split(',') if s.strip()]
        if args.debug and parsed_basic_land_sets:
            print(f"DEBUG: Parsed basic land set filter: {parsed_basic_land_sets}")

    # --- Discover images from source ---
    print("--- Discovering Images ---")
    if args.image_server_base_url:
        print(f"Using web server: {args.image_server_base_url}")
    else:
        print(f"Using local directory: {args.png_dir}")
    
    normalized_file_map, basic_land_details = discover_images(
        png_dir=args.png_dir,
        image_server_base_url=args.image_server_base_url,
        image_server_path_prefix=args.image_server_path_prefix,
        skip_basic_land=args.skip_basic_land,
        basic_land_sets_filter=parsed_basic_land_sets,
        debug=args.debug
    )
    
    if not normalized_file_map and not basic_land_details:
        print("No images found in source. Exiting.")
        return

    # --- Determine list of images to process ---
    image_sources_to_process: List[ImageSource] = []
    missing_cards_from_deck: List[str] = []

    try:
        if args.deck_list:
            print("\n--- Deck List Mode ---")
            image_sources_to_process, missing_cards_from_deck = process_deck_list(
                args.deck_list, normalized_file_map, basic_land_details,
                args.skip_basic_land, parsed_basic_land_sets, args.debug
            )
            if missing_cards_from_deck:
                write_missing_cards_file(args.deck_list, missing_cards_from_deck)
            
            if not image_sources_to_process and not args.png_out_dir:
                print("No images to print (after potential skips). Exiting.")
                return
            if image_sources_to_process:
                print(f"Prepared {len(image_sources_to_process)} image instances (excluding any skipped basic lands).")

        elif not args.png_out_dir:
            print("\n--- Directory Scan Mode (for PDF/PNG grid) ---")
            skipped_basics_count = 0
            
            # For directory scan, just use all images in normalized_file_map
            for norm_key, img_source in normalized_file_map.items():
                if args.skip_basic_land and norm_key in BASIC_LAND_NAMES:
                    if args.debug: print(f"DEBUG: Skipping basic land: {norm_key}")
                    skipped_basics_count += 1
                    continue
                image_sources_to_process.append(img_source)
            
            if args.skip_basic_land and skipped_basics_count > 0:
                print(f"  Skipped {skipped_basics_count} basic land files.")
            if not image_sources_to_process:
                print(f"No suitable PNGs found. Exiting.")
                return
            if args.sort:
                # Sort by original path/URL
                image_sources_to_process.sort(key=lambda x: x.original)
            print(f"Found {len(image_sources_to_process)} PNGs ({'sorted' if args.sort else 'unsorted'}).")
        
        elif args.png_out_dir and not args.deck_list:
            print("Error: --png-out-dir specified without a --deck-list. Nothing to do.")
            return

        # --- Perform Action: Copy PNGs or Generate Grid ---
        if args.png_out_dir:
            if not args.deck_list:
                print("Critical Error: --png-out-dir mode reached without a deck list. Please report this bug.")
                return
            if image_sources_to_process:
                copy_deck_pngs(image_sources_to_process, args.png_out_dir, args.debug)
            elif not missing_cards_from_deck:
                print("No images to copy (deck list may have contained only skipped basic lands or was empty).")

        else:  # Generate PDF or PNG grid
            if not image_sources_to_process:
                print("No images to generate grid output. Exiting.")
                return

            base_output_filename_final: str
            if args.output_file:
                base_output_filename_final = args.output_file
            elif args.deck_list:
                dl_bn = os.path.splitext(os.path.basename(args.deck_list))[0]
                dl_dir = os.path.dirname(args.deck_list)
                base_output_filename_final = os.path.join(dl_dir, dl_bn) if dl_dir else dl_bn
            else:
                base_output_filename_final = "MtgProxyOutput"

            name_for_pdf_label = os.path.basename(base_output_filename_final)

            if args.output_format == "pdf":
                output_pdf_with_ext = f"{base_output_filename_final}.pdf"
                
                if args.cameo:
                    # Warn about ignored arguments if --cameo is active
                    ignored_args_for_cameo = []
                    defaults = {
                        "page_margin": "5mm",
                        "image_spacing_pixels": 0,
                        "page_bg_color": "white",
                        "cut_lines": False,
                        "cut_line_length": "3mm",
                        "cut_line_color": "gray",
                        "cut_line_width_pt": 0.25
                    }
                    if args.page_margin != defaults["page_margin"]: ignored_args_for_cameo.append("--page-margin")
                    if args.image_spacing_pixels != defaults["image_spacing_pixels"]: ignored_args_for_cameo.append("--image-spacing-pixels")
                    if args.page_bg_color != defaults["page_bg_color"]: ignored_args_for_cameo.append("--page-bg-color")
                    if args.cut_lines: ignored_args_for_cameo.append("--cut-lines")
                    if args.cut_line_length != defaults["cut_line_length"]: ignored_args_for_cameo.append("--cut-line-length")
                    if args.cut_line_color != defaults["cut_line_color"]: ignored_args_for_cameo.append("--cut-line-color")
                    if args.cut_line_width_pt != defaults["cut_line_width_pt"]: ignored_args_for_cameo.append("--cut-line-width-pt")
                    
                    if ignored_args_for_cameo:
                        print(f"Warning: --cameo mode is active. The following options are ignored: {', '.join(ignored_args_for_cameo)}")
                    
                    create_pdf_cameo_style(
                        image_sources=image_sources_to_process,
                        output_pdf_file=output_pdf_with_ext,
                        paper_type_arg=validated_paper_type,
                        target_dpi=args.dpi,
                        image_cell_bg_color_str=args.image_cell_bg_color,
                        pdf_name_label=name_for_pdf_label,
                        debug=args.debug
                    )
                else:  # Original ReportLab PDF
                    create_pdf_grid(
                        image_sources=image_sources_to_process,
                        output_pdf_file=output_pdf_with_ext,
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
                        debug=args.debug
                    )
            elif args.output_format == "png":
                create_png_output(
                    image_files=image_sources_to_process,
                    base_output_filename=base_output_filename_final,
                    paper_type_str=validated_paper_type, dpi=args.dpi,
                    image_spacing_pixels=args.image_spacing_pixels,
                    page_margin_str=args.page_margin,
                    page_background_color_str=args.page_bg_color,
                    image_cell_background_color_str=args.image_cell_bg_color,
                    cut_lines=args.cut_lines,
                    cut_line_length_str=args.cut_line_length,
                    cut_line_color_str=args.cut_line_color,
                    cut_line_width_px=args.cut_line_width_px,
                    debug=args.debug
                )
            else:
                print(f"Error: Unknown output format '{args.output_format}'.")

    finally:
        # Clean up temporary files
        cleanup_temp_files()
        # Clean up any ImageSource temp files
        for img_source in image_sources_to_process:
            img_source.cleanup()

from typing import Any

if __name__ == "__main__":
    main()

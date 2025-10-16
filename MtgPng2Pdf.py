#!/usr/bin/env python3

import os
import glob
import argparse
import unicodedata
import re
import shutil
from typing import List, Tuple, Dict, Optional, Set, Union, Any, NamedTuple
from collections import defaultdict
import math
import random
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, quote
import io

# --- Add requests dependency for uploading ---
# Note: This script now requires the 'requests' library for the --upload-to-server feature.
# Install it using: pip install requests
try:
    import requests
except ImportError:
    print("Error: The 'requests' library is required for the --upload-to-server feature.")
    print("Please install it using: pip install requests")
    exit(1)

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

# --- Web Server Upload Functions ---
def check_server_file_exists(url: str, debug: bool = False) -> bool:
    """Check if a file already exists at a given URL using a HEAD request."""
    if not url:
        return False
    if debug:
        print(f"DEBUG: Checking for file existence at: {url}")
    try:
        r = requests.head(url, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            if debug: print(f"DEBUG: File exists (200 OK) at {url}")
            return True
        if r.status_code == 404:
            if debug: print(f"DEBUG: File not found (404) at {url}")
            return False
        print(f"Warning: Received status {r.status_code} when checking {url}. Assuming it does not exist.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Warning: Network error while checking {url}: {e}. Assuming it does not exist.")
        return False

def upload_file_to_server(url: str, file_bytes: bytes, mime_type: str, debug: bool = False) -> bool:
    """Uploads file content (bytes) to a server URL using PUT."""
    if not url:
        print("Error: Cannot upload file, server URL is not configured.")
        return False
    if not file_bytes:
        print("Warning: No file content (bytes) to upload.")
        return False

    print(f"Uploading to: {url}")
    headers = {'Content-Type': mime_type}
    try:
        r = requests.put(url, data=file_bytes, headers=headers, timeout=60)
        r.raise_for_status()  # Raises an exception for 4xx/5xx status codes
        if 200 <= r.status_code < 300:
            print(f"Successfully uploaded. URL: {url}")
            return True
        else:
            # This part is less likely to be reached due to raise_for_status
            print(f"Error: Upload failed with status {r.status_code}.")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error: Upload failed due to a network error: {e}")
        return False

# --- Web Server Functions ---
def list_webdav_directory(base_url: str, path: str = "/", debug: bool = False) -> List[Dict[str, str]]:
    """
    List files in a directory using WebDAV PROPFIND, with a fallback to simple HTTP listing.
    Returns a list of dicts with 'name' and 'href' (as a full URL) keys.
    """
    url = urljoin(base_url, path)
    if debug: print(f"DEBUG: Listing directory: {url}")
    
    # Build PROPFIND request body
    propfind_body = '''<?xml version="1.0" encoding="utf-8"?><D:propfind xmlns:D="DAV:"><D:prop><D:displayname/><D:resourcetype/></D:prop></D:propfind>'''
    
    req = urllib.request.Request(url, data=propfind_body.encode('utf-8'), headers={'Content-Type': 'application/xml; charset=utf-8', 'Depth': '1'}, method='PROPFIND')
    
    try:
        with urllib.request.urlopen(req) as response: content = response.read().decode('utf-8')
        
        # Parse XML response
        root = ET.fromstring(content); files = []; ns = {'d': 'DAV:'}
        
        for response_elem in root.findall('.//d:response', ns):
            href_elem = response_elem.find('d:href', ns)
            displayname_elem = response_elem.find('.//d:displayname', ns)
            resourcetype_elem = response_elem.find('.//d:resourcetype', ns)
            
            if href_elem is not None:
                relative_href = href_elem.text
                # Skip directories (they have a <collection/> element)
                if resourcetype_elem is not None and resourcetype_elem.find('d:collection', ns) is not None: continue
                
                # Get filename
                if displayname_elem is not None and displayname_elem.text: filename = displayname_elem.text
                else: filename = os.path.basename(urllib.parse.unquote(relative_href.rstrip('/')))
                
                if filename and filename.lower().endswith('.png'):
                    # Construct the full URL for the file
                    full_url = urljoin(base_url, relative_href)
                    files.append({'name': filename, 'href': full_url})
        
        if debug: print(f"DEBUG: Found {len(files)} PNG files in directory")
        return files
        
    except urllib.error.HTTPError as e:
        # If PROPFIND is not allowed, fall back to simple HTTP listing
        if e.code == 405: return list_http_directory(url, debug)
        else: print(f"Error listing directory: HTTP {e.code} - {e.reason}"); return []
    except Exception as e: print(f"Error listing directory: {e}"); return []

def list_http_directory(url: str, debug: bool = False) -> List[Dict[str, str]]:
    """
    Fallback method to list files from a simple HTTP directory listing.
    Parses HTML for links to PNG files. Returns full URLs.
    """
    if not url.endswith('/'): url += '/'
    if debug: print(f"DEBUG: Attempting HTTP directory listing: {url}")
    try:
        with urllib.request.urlopen(url) as response: content = response.read().decode('utf-8')
        
        # Simple regex to find links to PNG files
        png_pattern = r'href="([^"]+\.png)"'; matches = re.findall(png_pattern, content, re.IGNORECASE)
        
        files = []
        for match in matches:
            filename = os.path.basename(urllib.parse.unquote(match))
            full_url = urljoin(url, match)
            files.append({'name': filename, 'href': full_url})
        
        if debug: print(f"DEBUG: Found {len(files)} PNG files in HTTP directory listing")
        return files
    except Exception as e: print(f"Error listing HTTP directory: {e}"); return []

def download_image(url: str, dest_path: Optional[str] = None, debug: bool = False) -> Optional[str]:
    """
    Download an image from URL. If dest_path is None, saves to a temp file.
    Returns the path to the downloaded file, or None on error.
    """
    if debug: print(f"DEBUG: Downloading image from {url}")
    try:
        # Create temp file if no destination specified
        if dest_path is None:
            fd, dest_path = tempfile.mkstemp(suffix='.png'); os.close(fd)
            _temp_files.add(dest_path)
        
        # Download the file
        urllib.request.urlretrieve(url, dest_path)
        
        if debug: print(f"DEBUG: Downloaded to {dest_path}")
        return dest_path
    except Exception as e:
        print(f"Error downloading image from {url}: {e}")
        if dest_path and os.path.exists(dest_path):
            os.remove(dest_path); _temp_files.discard(dest_path)
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
        if not self.is_url: return self.local_path
        if self.temp_file is None: self.temp_file = download_image(self.original, debug=debug)
        return self.temp_file
    def cleanup(self):
        """Clean up any temporary files"""
        if self.temp_file and os.path.exists(self.temp_file):
            try: os.remove(self.temp_file); _temp_files.discard(self.temp_file)
            except: pass
            self.temp_file = None
    def __del__(self): self.cleanup()

# --- PNG discovery function ---
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

# --- Cameo PDF Generation Code ---

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

class CameoPaperSize: LETTER = "letter"; A4 = "a4"
class CameoCardSize: STANDARD = "standard"; JAPANESE = "japanese"
def calculate_max_print_bleed_cameo(x_pos: List[int], y_pos: List[int], width: int, height: int) -> int:
    if len(x_pos) == 1 and len(y_pos) == 1: return 0
    x_border_max = 100000
    if len(x_pos) >= 2:
        sorted_x_pos = sorted(x_pos); x_pos_0 = sorted_x_pos[0]; x_pos_1 = sorted_x_pos[1]
        x_border_max = math.ceil((x_pos_1 - x_pos_0 - width) / 2)
        if x_border_max < 0: x_border_max = 100000
    y_border_max = 100000
    if len(y_pos) >= 2:
        sorted_y_pos = sorted(y_pos); y_pos_0 = sorted_y_pos[0]; y_pos_1 = sorted_y_pos[1]
        y_border_max = math.ceil((y_pos_1 - y_pos_0 - height) / 2)
        if y_border_max < 0: y_border_max = 100000
    return min(x_border_max, y_border_max) + 1
def draw_card_with_border_cameo(card_image: Image.Image, base_image: Image.Image, box: tuple[int, int, int, int], print_bleed: int, cell_bg_color_pil: Union[str, Tuple[int, int, int], None]):
    origin_x, origin_y, origin_width, origin_height = box
    if cell_bg_color_pil is not None:
        draw = ImageDraw.Draw(base_image)
        if print_bleed > 0: max_offset = print_bleed - 1 if print_bleed > 0 else 0; cell_rect_x0 = origin_x - max_offset; cell_rect_y0 = origin_y - max_offset; cell_rect_x1 = origin_x + origin_width + max_offset; cell_rect_y1 = origin_y + origin_height + max_offset
        else: cell_rect_x0 = origin_x; cell_rect_y0 = origin_y; cell_rect_x1 = origin_x + origin_width; cell_rect_y1 = origin_y + origin_height
        draw.rectangle([cell_rect_x0, cell_rect_y0, cell_rect_x1, cell_rect_y1], fill=cell_bg_color_pil)
    for i in reversed(range(print_bleed)):
        card_image_resized_for_this_iteration = card_image.resize((origin_width + (2 * i), origin_height + (2 * i)))
        paste_pos_x = origin_x - i; paste_pos_y = origin_y - i
        base_image.paste(card_image_resized_for_this_iteration, (paste_pos_x, paste_pos_y), card_image_resized_for_this_iteration if card_image_resized_for_this_iteration.mode == 'RGBA' else None)
def draw_card_layout_cameo(card_images: List[Image.Image], base_image: Image.Image, num_rows: int, num_cols: int, x_pos_layout: List[int], y_pos_layout: List[int], card_width_layout: int, card_height_layout: int, print_bleed_layout_units: int, crop_percentage: float, ppi_ratio: float, extend_corners_src_px: int, flip: bool, cell_bg_color_pil: Union[str, Tuple[int, int, int], None]):
    num_slots_on_page = num_rows * num_cols
    for i, original_card_pil_image in enumerate(card_images):
        if i >= num_slots_on_page: break
        current_card_image = original_card_pil_image
        slot_x_on_page_scaled = math.floor(x_pos_layout[i % num_cols] * ppi_ratio); slot_y_on_page_scaled = math.floor(y_pos_layout[i // num_cols] * ppi_ratio)
        if crop_percentage > 0: card_w, card_h = current_card_image.size; crop_w_px = math.floor(card_w / 2 * (crop_percentage / 100.0)); crop_h_px = math.floor(card_h / 2 * (crop_percentage / 100.0)); current_card_image = current_card_image.crop((crop_w_px, crop_h_px, card_w - crop_w_px, card_h - crop_h_px))
        if extend_corners_src_px > 0: current_card_image = current_card_image.crop((extend_corners_src_px, extend_corners_src_px, current_card_image.width - extend_corners_src_px, current_card_image.height - extend_corners_src_px))
        extend_corners_page_px_scaled = math.floor(extend_corners_src_px * ppi_ratio)
        card_render_width_scaled = math.floor(card_width_layout * ppi_ratio) - (2 * extend_corners_page_px_scaled); card_render_height_scaled = math.floor(card_height_layout * ppi_ratio) - (2 * extend_corners_page_px_scaled)
        paste_box_for_card_content = (slot_x_on_page_scaled + extend_corners_page_px_scaled, slot_y_on_page_scaled + extend_corners_page_px_scaled, card_render_width_scaled, card_render_height_scaled)
        final_print_bleed_iterations = math.ceil(print_bleed_layout_units * ppi_ratio) + extend_corners_page_px_scaled
        draw_card_with_border_cameo(current_card_image, base_image, paste_box_for_card_content, final_print_bleed_iterations, cell_bg_color_pil)
def create_pdf_cameo_style(image_sources: List[ImageSource], output_path_or_buffer: Union[str, io.BytesIO], paper_type_arg: str, target_dpi: int, image_cell_bg_color_str: str, pdf_name_label: Optional[str], label_font_size_base: int, debug: bool = False):
    print(f"\n--- Cameo PDF Generation (PIL-based) ---")
    if isinstance(output_path_or_buffer, str): print(f"Output file: {output_path_or_buffer}")
    else: print(f"Output target: In-memory buffer (for server upload)")
    default_cell_bg_color = "black"
    if image_cell_bg_color_str.lower() != default_cell_bg_color: print(f"  Image Cell Background Color: {image_cell_bg_color_str}")
    if paper_type_arg.lower() == "letter": cameo_paper_key = CameoPaperSize.LETTER
    elif paper_type_arg.lower() == "a4": cameo_paper_key = CameoPaperSize.A4
    else: print(f"Error: --cameo PDF generation: Paper type '{paper_type_arg}' is not directly supported by embedded cameo layouts."); return
    cameo_card_key = CameoCardSize.STANDARD
    try: paper_layout_config = LAYOUTS_DATA["paper_layouts"][cameo_paper_key]; card_layout_config = paper_layout_config["card_layouts"][cameo_card_key]
    except KeyError: print(f"Error: Layout for paper '{cameo_paper_key}' and card size '{cameo_card_key}' not found."); return
    num_rows = len(card_layout_config["y_pos"]); num_cols = len(card_layout_config["x_pos"]); num_cards_per_page = num_rows * num_cols
    layout_base_ppi = 300.0; ppi_ratio = target_dpi / layout_base_ppi
    page_width_px_scaled = math.floor(paper_layout_config["width"] * ppi_ratio); page_height_px_scaled = math.floor(paper_layout_config["height"] * ppi_ratio)
    card_slot_width_layout = card_layout_config["width"]; card_slot_height_layout = card_layout_config["height"]
    crop_percentage_on_source = 0.0; extend_corners_on_source_px = 0; pdf_save_quality = 75
    max_print_bleed_layout_units = calculate_max_print_bleed_cameo(card_layout_config["x_pos"], card_layout_config["y_pos"], card_slot_width_layout, card_slot_height_layout)
    if debug: print(f"DEBUG CAMEO: Paper Key: {cameo_paper_key}, Card Key: {cameo_card_key}"); print(f"DEBUG CAMEO: Grid: {num_cols}x{num_rows} ({num_cards_per_page} cards/page)")
    script_dir = os.path.dirname(os.path.abspath(__file__)); asset_dir_cameo = os.path.join(script_dir, "assets"); registration_filename = f'{cameo_paper_key}_registration.jpg'; registration_path = os.path.join(asset_dir_cameo, registration_filename)
    master_page_background: Optional[Image.Image] = None
    if os.path.exists(registration_path):
        try:
            reg_im_original = Image.open(registration_path); reg_im_scaled = reg_im_original.resize((page_width_px_scaled, page_height_px_scaled))
            if reg_im_scaled.mode != 'RGB': reg_im_scaled = reg_im_scaled.convert('RGB')
            master_page_background = reg_im_scaled
            if debug: print(f"DEBUG CAMEO: Loaded registration mark: {registration_path}")
        except Exception as e_reg: print(f"  Warning: Could not load registration image: {e_reg}")
    if master_page_background is None: master_page_background = Image.new("RGB", (page_width_px_scaled, page_height_px_scaled), "white")
    pil_cell_bg_color: Union[str, Tuple[int,int,int], None] = image_cell_bg_color_str
    all_pil_pages: List[Image.Image] = []; total_images_to_process = len(image_sources)
    for page_start_index in range(0, total_images_to_process, num_cards_per_page):
        current_page_pil_image = master_page_background.copy()
        image_sources_for_this_page = image_sources[page_start_index : page_start_index + num_cards_per_page]
        pil_card_images_for_page: List[Image.Image] = []
        for img_source in image_sources_for_this_page:
            try:
                local_path = img_source.get_local_path(debug)
                if local_path: img = Image.open(local_path); img = img.convert('RGBA'); pil_card_images_for_page.append(img)
                else: raise Exception("Failed to get local path")
            except Exception as e:
                print(f"  Warning: Could not process image '{img_source.original}': {e}")
                placeholder_w = int(TARGET_IMG_WIDTH_INCHES * target_dpi); placeholder_h = int(TARGET_IMG_HEIGHT_INCHES * target_dpi)
                placeholder = Image.new("RGBA", (placeholder_w, placeholder_h), (255, 192, 203, 255)); draw_placeholder = ImageDraw.Draw(placeholder)
                try: font_placeholder = ImageFont.load_default(); draw_placeholder.text((5,5), "Error\nLoading", fill="black", font=font_placeholder)
                except: draw_placeholder.text((5,5), "Error", fill="black")
                pil_card_images_for_page.append(placeholder)
        draw_card_layout_cameo(card_images=pil_card_images_for_page, base_image=current_page_pil_image, num_rows=num_rows, num_cols=num_cols, x_pos_layout=card_layout_config["x_pos"], y_pos_layout=card_layout_config["y_pos"], card_width_layout=card_slot_width_layout, card_height_layout=card_slot_height_layout, print_bleed_layout_units=max_print_bleed_layout_units, crop_percentage=crop_percentage_on_source, ppi_ratio=ppi_ratio, extend_corners_src_px=extend_corners_on_source_px, flip=False, cell_bg_color_pil=pil_cell_bg_color)
        page_num_for_label = (page_start_index // num_cards_per_page) + 1; template_name = card_layout_config.get("template", "unknown_template")
        base_label_part = f"template: {template_name}, sheet: {page_num_for_label}"
        if pdf_name_label: label_text = f"name: {pdf_name_label}, {base_label_part}"
        else: label_text = base_label_part
        try:
            draw_page_text = ImageDraw.Draw(current_page_pil_image)
            text_x_pos = math.floor((paper_layout_config["width"] - 180) * ppi_ratio); text_y_pos = math.floor((paper_layout_config["height"] - 180) * ppi_ratio)
            font_size_scaled = math.floor(label_font_size_base * ppi_ratio)
            page_font = None
            try: script_dir = os.path.dirname(os.path.abspath(__file__)); font_path = os.path.join(script_dir, "assets", "DejaVuSans.ttf"); page_font = ImageFont.truetype(font_path, size=font_size_scaled)
            except IOError: print("  Warning: Font 'assets/DejaVuSans.ttf' not found."); print("  Falling back to tiny default font. Please download and place the font for scalable labels.");
            except Exception: pass
            if page_font: draw_page_text.text((text_x_pos, text_y_pos), label_text, fill=(0,0,0), anchor="ra", font=page_font)
        except Exception as e_font:
            if debug: print(f"DEBUG CAMEO: Could not draw page label: {e_font}")
        all_pil_pages.append(current_page_pil_image)
    if not all_pil_pages: print("Cameo PDF: No pages generated."); return
    try:
        all_pil_pages[0].save(output_path_or_buffer, format='PDF', save_all=True, append_images=all_pil_pages[1:], resolution=float(target_dpi), quality=pdf_save_quality)
        if isinstance(output_path_or_buffer, str): print(f"Cameo PDF generation successful: {output_path_or_buffer} ({len(all_pil_pages)} page(s))")
        else: print(f"Cameo PDF generation to memory buffer successful ({len(all_pil_pages)} page(s))")
    except Exception as e: print(f"Error saving Cameo PDF: {e}")

# --- Helper Functions ---

def normalize_card_name(name: str) -> str:
    """
    A robust function to normalize a card name for consistent key generation.
    Removes accents, punctuation, and whitespace, and converts to lowercase.
    """
    name = name.lower().strip()
    # Decompose unicode characters (like accents) into base characters
    normalized_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    # Remove common punctuation and whitespace used as separators
    normalized_name = re.sub(r"[',\.:()\[\]\s_]", "", normalized_name)
    # Remove any remaining non-alphanumeric characters (except hyphens if needed, but we remove them here for the key)
    normalized_name = re.sub(r"[^a-z0-9-]", "", normalized_name)
    return normalized_name.strip()

# Data structure for a parsed deck list line
class DecklistEntry(NamedTuple):
    count: int
    card_name: str
    set_code: Optional[str]
    collector_number: Optional[str]
    original_line: str

# Regex to parse Moxfield-style deck list lines
MOXFIELD_LINE_RE = re.compile(
    # 1. Capture count and trailing space(s)
    r"^\s*(?P<count>\d+)\s+"
    # 2. Capture card name (non-greedy)
    r"(?P<name>.+?)"
    # 3. An optional group for the set, which itself contains an optional group for the number.
    #    The set part is required for this block to match.
    r"(?:\s+\((?P<set>[A-Z0-9]{3,5})\)"
    #    The number part is now optional within the set block.
    r"(?:\s+(?P<number>[\w\d\s\-\★]+))?)?"
    # 4. Match any trailing whitespace and the end of the line.
    r"\s*$",
    # This flag makes the whole regex case-insensitive for set codes like (ice) or (ICE).
    re.IGNORECASE
)

def parse_moxfield_line(line: str) -> Optional[DecklistEntry]:
    """Parses a deck list line into its components using the main regex."""
    match = MOXFIELD_LINE_RE.match(line)
    if not match:
        # Fallback for simple "COUNT NAME" format if the main regex fails.
        # This handles lines without any (SET) information.
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            return DecklistEntry(
                count=int(parts[0]),
                card_name=parts[1].strip(),
                set_code=None,
                collector_number=None,
                original_line=line
            )
        return None
    
    data = match.groupdict()
    
    return DecklistEntry(
        count=int(data['count']),
        card_name=data['name'].strip(),
        # We still call .lower() to ensure consistency in the rest of the script
        set_code=data['set'].strip().lower() if data.get('set') else None,
        collector_number=data['number'].strip().lower() if data.get('number') else None,
        original_line=line
    )

def parse_variant_filename(filename: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parses a card filename like 'Memory-Lapse_ema_60.png' or 'Dandân_arn_12.png'.
    Returns (normalized_name, set_code, collector_number)
    """
    basename_no_ext = os.path.splitext(os.path.basename(filename))[0]
    # Split by either hyphen or underscore to handle different naming conventions
    parts = re.split(r'[-_]', basename_no_ext)

    # Heuristic: If there are at least 3 parts, the last two are likely set/number.
    # This handles "Card-Name-SET-NUM" and "Card_Name_SET_NUM".
    if len(parts) >= 3:
        # A simple check to see if the second-to-last part looks like a set code.
        # Most set codes are 3-5 alphanumeric characters.
        is_set_like = 3 <= len(parts[-2]) <= 5 and re.match(r'^[a-z0-9]+$', parts[-2].lower())

        if is_set_like:
            collector_number = parts[-1].lower()
            set_code = parts[-2].lower()
            # Everything before the set and number is the card name.
            # We join them without separators because normalize_card_name will remove them anyway.
            name_str = "".join(parts[:-2])
            normalized_name = normalize_card_name(name_str)
            return normalized_name, set_code, collector_number

    # If the heuristic fails or there are fewer than 3 parts,
    # treat the whole thing as the name. This handles "Sol Ring.png".
    return normalize_card_name(basename_no_ext), None, None

def process_deck_list(
    deck_list_path: str,
    all_cards_map: Dict[str, List[ImageSource]],
    skip_basic_land: bool,
    basic_land_sets_filter: Optional[List[str]],
    basic_land_set_mode: str,
    spell_sets_filter: Optional[List[str]],
    spell_set_mode: str,
    debug: bool = False
) -> Tuple[List[ImageSource], List[str]]:
    """
    Processes a deck list, aggregating card counts before finding images.
    """
    images_to_print: List[ImageSource] = []
    missing_card_names: List[str] = []
    skipped_basic_lands_count: Dict[str, int] = defaultdict(int)

    fully_specific_requests: Dict[Tuple[str, str, str], int] = defaultdict(int)
    set_specific_requests: Dict[Tuple[str, str], int] = defaultdict(int)
    generic_requests: Dict[str, int] = defaultdict(int)
    original_card_names: Dict[str, str] = {}

    # --- Pass 1: Parse and Aggregate all lines from the deck list ---
    try:
        with open(deck_list_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                if not line or not line[0].isdigit():
                    if debug and line:
                        print(f"DEBUG: Skipping non-data line {line_num}: '{line}'")
                    continue

                entry = parse_moxfield_line(line)
                if not entry:
                    print(f"  Warning: Skipping malformed data line {line_num}: '{line}'")
                    missing_card_names.append(line)
                    continue

                normalized_name = normalize_card_name(entry.card_name)
                if normalized_name not in original_card_names:
                    original_card_names[normalized_name] = entry.card_name

                if entry.set_code and entry.collector_number:
                    key = (normalized_name, entry.set_code, entry.collector_number)
                    fully_specific_requests[key] += entry.count
                elif entry.set_code:
                    key = (normalized_name, entry.set_code)
                    set_specific_requests[key] += entry.count
                else:
                    generic_requests[normalized_name] += entry.count

    except FileNotFoundError:
        print(f"Error: Deck list file not found: {deck_list_path}")
        return [], []

    used_sources: Set[ImageSource] = set()
    
    # --- Helper function for card selection to ensure variety ---
    def select_cards(pool: List[ImageSource], num_to_select: int) -> List[ImageSource]:
        if not pool:
            return []
        
        # Create a shuffled copy of the pool to pick from
        shuffled_pool = pool[:]
        random.shuffle(shuffled_pool)
        
        selected: List[ImageSource] = []
        pool_size = len(shuffled_pool)
        for i in range(num_to_select):
            # Cycle through the shuffled pool to ensure maximum variety
            selected.append(shuffled_pool[i % pool_size])
        
        return selected

    # --- Pass 2: Process FULLY-SPECIFIC requests first ---
    if debug and fully_specific_requests: print("DEBUG: Processing fully-specific card requests...")
    for (normalized_name, set_code, collector_number), count in fully_specific_requests.items():
        found_source: Optional[ImageSource] = None
        for source in all_cards_map.get(normalized_name, []):
            _, f_set, f_num = parse_variant_filename(source.original)
            if f_set == set_code and f_num == collector_number:
                found_source = source
                break
        
        original_name = original_card_names.get(normalized_name, normalized_name)
        log_line = f"{count}x '{original_name} ({set_code.upper()}) {collector_number}'"

        if found_source:
            if debug: print(f"DEBUG:   FOUND specific: {log_line}")
            images_to_print.extend([found_source] * count)
            used_sources.add(found_source)
        else:
            print(f"  NOT FOUND (Fully-Specific): {log_line}")
            missing_card_names.append(f"{count}x {original_name} ({set_code.upper()}) {collector_number}")

    # --- Pass 3: Process SET-SPECIFIC requests ---
    if debug and set_specific_requests: print("DEBUG: Processing set-specific card requests...")
    for (normalized_name, set_code), count in set_specific_requests.items():
        original_name = original_card_names.get(normalized_name, normalized_name)
        log_line_base = f"{count}x '{original_name} ({set_code.upper()})'"

        available_sources = all_cards_map.get(normalized_name, [])
        candidate_pool = [src for src in available_sources if src not in used_sources and parse_variant_filename(src.original)[1] == set_code]
        
        if not candidate_pool:
            print(f"  NOT FOUND (Set-Specific): No available images for {log_line_base}")
            missing_card_names.append(f"{count}x {original_name} ({set_code.upper()})")
            continue
            
        selected_sources = select_cards(candidate_pool, count)
        if debug: print(f"DEBUG:   Selected {len(selected_sources)} versions for {log_line_base}")
        
        images_to_print.extend(selected_sources)
        for src in selected_sources: used_sources.add(src)

    # --- Pass 4: Process GENERIC requests ---
    if debug and generic_requests: print("DEBUG: Processing generic card requests...")
    for normalized_name, count in generic_requests.items():
        original_name = original_card_names.get(normalized_name, normalized_name)

        is_basic_land = normalized_name in BASIC_LAND_NAMES
        if is_basic_land and skip_basic_land:
            if debug: print(f"DEBUG: Skipping basic land: {count}x '{original_name}'")
            skipped_basic_lands_count[original_name] += count
            continue
            
        available_sources = all_cards_map.get(normalized_name, [])
        candidate_pool = [src for src in available_sources if src not in used_sources]
        
        if not candidate_pool:
            print(f"  NOT FOUND (Generic): No available images for {count}x '{original_name}'")
            missing_card_names.append(f"{count}x {original_name}")
            continue
        
        # Apply global set filters with preference/force logic
        final_pool = candidate_pool
        if is_basic_land and basic_land_sets_filter:
            filtered_pool = [src for src in candidate_pool if parse_variant_filename(src.original)[1] in basic_land_sets_filter]
            if filtered_pool:
                final_pool = filtered_pool
            elif basic_land_set_mode == 'force':
                print(f"  NOT FOUND (Basic Land): No '{original_name}' matching required sets: {basic_land_sets_filter}")
                missing_card_names.append(f"{count}x {original_name} (Set Mismatch: {basic_land_sets_filter})")
                continue
            else: # 'prefer' mode with no matches
                 print(f"  WARN: No '{original_name}' found in preferred sets {basic_land_sets_filter}. Falling back to all available sets.")
        
        elif not is_basic_land and spell_sets_filter:
            filtered_pool = [src for src in candidate_pool if parse_variant_filename(src.original)[1] in spell_sets_filter]
            if filtered_pool:
                final_pool = filtered_pool
            elif spell_set_mode == 'force':
                print(f"  NOT FOUND (Spell): No '{original_name}' matching required sets: {spell_sets_filter}")
                missing_card_names.append(f"{count}x {original_name} (Set Mismatch: {spell_sets_filter})")
                continue
            else: # 'prefer' mode with no matches
                print(f"  WARN: No '{original_name}' found in preferred sets {spell_sets_filter}. Falling back to all available sets.")

        selected_sources = select_cards(final_pool, count)
        images_to_print.extend(selected_sources)
        for src in selected_sources: used_sources.add(src)

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
def create_pdf_grid(image_sources: List[ImageSource], output_path_or_buffer: Union[str, io.BytesIO], **kwargs):
    if isinstance(output_path_or_buffer, str): print(f"\n--- PDF Generation Settings (ReportLab: {output_path_or_buffer}) ---")
    else: print(f"\n--- PDF Generation Settings (ReportLab to memory buffer) ---")
    paper_type_str = kwargs.get("paper_type_str")
    if not image_sources: print("No images for PDF."); return
    local_paths = []
    for img_source in image_sources:
        local_path = img_source.get_local_path(kwargs.get("debug", False))
        if local_path: local_paths.append(local_path)
        else: print(f"Warning: Could not get image from {img_source.original}"); local_paths.append(None)
    paper_width_pt, paper_height_pt = PAPER_SIZES_PT[paper_type_str]
    c = canvas.Canvas(output_path_or_buffer, pagesize=(paper_width_pt, paper_height_pt))
    dpi = kwargs.get("dpi", 300); page_margin_str = kwargs.get("page_margin_str", "5mm"); image_spacing_pixels = kwargs.get("image_spacing_pixels", 0)
    page_bg_color_str = kwargs.get("page_background_color_str", "white"); image_cell_bg_color_str = kwargs.get("image_cell_background_color_str", "black")
    cut_lines = kwargs.get("cut_lines", False); cut_line_length_str = kwargs.get("cut_line_length_str", "3mm"); cut_line_color_str = kwargs.get("cut_line_color_str", "gray"); cut_line_width_pt = kwargs.get("cut_line_width_pt", 0.25)
    print(f"  Paper: {paper_type_str} ({paper_width_pt/inch:.2f}\" x {paper_height_pt/inch:.2f}\")"); print(f"  DPI: {dpi}, Image Size: {TARGET_IMG_WIDTH_INCHES}\" x {TARGET_IMG_HEIGHT_INCHES}\"")
    try: page_margin_px = parse_dimension_to_pixels(page_margin_str, dpi, default_unit_is_mm=True)
    except ValueError as e: print(f"Error parsing page margin '{page_margin_str}': {e}. Using 0px."); page_margin_px = 0
    page_margin_pt = page_margin_px * (inch / dpi); img_spacing_pt = image_spacing_pixels * (inch / dpi)
    target_img_width_pt = TARGET_IMG_WIDTH_INCHES * inch; target_img_height_pt = TARGET_IMG_HEIGHT_INCHES * inch
    grid_cols, grid_rows = (3,3) if paper_type_str == "letter" else (3,4)
    print(f"  Grid: {grid_cols}x{grid_rows} cards per page."); print(f"  Margins: {page_margin_str} ({page_margin_pt:.2f}pt), Spacing: {image_spacing_pixels}px ({img_spacing_pt:.2f}pt)")
    available_width_pt = paper_width_pt - 2 * page_margin_pt; available_height_pt = paper_height_pt - 2 * page_margin_pt
    total_card_width_pt = grid_cols * target_img_width_pt + (grid_cols - 1) * img_spacing_pt; total_card_height_pt = grid_rows * target_img_height_pt + (grid_rows - 1) * img_spacing_pt
    start_x_pt = page_margin_pt + (available_width_pt - total_card_width_pt) / 2; start_y_pt = paper_height_pt - page_margin_pt - (available_height_pt - total_card_height_pt) / 2 - target_img_height_pt
    if total_card_width_pt > available_width_pt or total_card_height_pt > available_height_pt: print("  Warning: Cards + spacing might exceed available page area.")
    images_per_page = grid_cols * grid_rows; total_images = len(local_paths); num_pages = (total_images + images_per_page - 1) // images_per_page
    page_bg_color_rl = getattr(reportlab_colors, page_bg_color_str.lower(), reportlab_colors.white); cell_bg_color_rl = getattr(reportlab_colors, image_cell_bg_color_str.lower(), reportlab_colors.black); cut_line_color_rl = getattr(reportlab_colors, cut_line_color_str.lower(), reportlab_colors.gray)
    try: cut_line_len_px = parse_dimension_to_pixels(cut_line_length_str, dpi, default_unit_is_mm=True); cut_line_len_pt = cut_line_len_px * (inch / dpi)
    except ValueError as e: print(f"Error parsing cut line length '{cut_line_length_str}': {e}. Using 0px."); cut_line_len_pt = 0
    for page_num in range(num_pages):
        c.setFillColor(page_bg_color_rl); c.rect(0, 0, paper_width_pt, paper_height_pt, fill=1, stroke=0)
        for i in range(images_per_page):
            img_idx = page_num * images_per_page + i
            if img_idx >= total_images: break
            row = i // grid_cols; col = i % grid_cols
            x = start_x_pt + col * (target_img_width_pt + img_spacing_pt); y = start_y_pt - row * (target_img_height_pt + img_spacing_pt)
            c.setFillColor(cell_bg_color_rl); c.rect(x, y, target_img_width_pt, target_img_height_pt, fill=1, stroke=0)
            if local_paths[img_idx]:
                try: c.drawImage(local_paths[img_idx], x, y, width=target_img_width_pt, height=target_img_height_pt, mask='auto')
                except Exception as e: print(f"  Warning: Could not draw image {img_idx} on page {page_num+1}: {e}"); c.setFillColorRGB(1, 0, 0); c.rect(x, y, target_img_width_pt, target_img_height_pt, fill=1, stroke=0); c.setFillColorRGB(0,0,0); c.drawCentredString(x + target_img_width_pt/2, y + target_img_height_pt/2, "Error")
            if cut_lines and cut_line_len_pt > 0:
                c.setStrokeColor(cut_line_color_rl); c.setLineWidth(cut_line_width_pt)
                c.line(x, y + target_img_height_pt, x - cut_line_len_pt, y + target_img_height_pt); c.line(x + target_img_width_pt, y + target_img_height_pt, x + target_img_width_pt + cut_line_len_pt, y + target_img_height_pt); c.line(x, y, x - cut_line_len_pt, y); c.line(x + target_img_width_pt, y, x + target_img_width_pt + cut_line_len_pt, y); c.line(x, y + target_img_height_pt, x, y + target_img_height_pt + cut_line_len_pt); c.line(x, y, x, y - cut_line_len_pt); c.line(x + target_img_width_pt, y + target_img_height_pt, x + target_img_width_pt, y + target_img_height_pt + cut_line_len_pt); c.line(x + target_img_width_pt, y, x + target_img_width_pt, y - cut_line_len_pt)
        c.showPage()
    c.save()
    if isinstance(output_path_or_buffer, str): print(f"ReportLab PDF generation complete: {output_path_or_buffer} ({num_pages} page(s))")
    else: print(f"ReportLab PDF generation to memory buffer complete ({num_pages} page(s))")
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
def cleanup_temp_files():
    global _temp_files
    for temp_file in _temp_files:
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass
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
        help="Path to deck list. Supports 'COUNT NAME', 'COUNT NAME (SET)', and 'COUNT NAME (SET) NUM' formats."
    )
    mode_group.add_argument("--output-file", type=str, default=None, help="Base name for local PDF/PNG grid output, or just the filename for server upload. Extension auto-added. Defaults to MtgProxyOutput, or <deck_list_name> if --deck-list is used.")
    mode_group.add_argument("--output-format", type=str, default="pdf", choices=["pdf", "png"], help="Format for grid layout output (pdf or png). Ignored if --png-out-dir is used.")
    mode_group.add_argument("--png-out-dir", type=str, default=None, help="Output directory for copying PNGs from deck list. If set, grid generation is skipped.")
    
    # --- MODIFIED: Renamed to be more generic ---
    server_group = parser.add_argument_group('Image Server Options')
    # --- MODIFIED: Help text updated, dual purpose explained ---
    server_group.add_argument(
        "--image-server-base-url", type=str, default=None,
        help="Base URL of the image server. If provided, images will be fetched from this server instead of --png-dir. "
             "If --upload-to-server is used, output files will be PUT to this server instead of being saved locally. "
             "Required if --upload-to-server is set."
    )
    # --- MODIFIED: Default and help text updated ---
    server_group.add_argument(
        "--image-server-path-prefix", type=str, default="/local_art",
        help="Base path for the art URL. Used for both PNG card image retrieval and, if --upload-to-server is used, "
             "constructing the output file path for the PDF."
    )
    # --- NEW ---
    server_group.add_argument(
        "--image-server-png-dir", type=str, default="/",
        help="Relative path (from --image-server-path-prefix) to the directory containing the source PNG files."
    )
    
    # --- MODIFIED: Renamed to be more generic ---
    server_upload_group = parser.add_argument_group('Image Server Upload Options')
    server_upload_group.add_argument(
        "--upload-to-server", action="store_true",
        help="Upload the generated PDF to the image server instead of saving it locally. "
             "Requires --image-server-base-url."
    )
    # --- MODIFIED: Renamed from --output-server-path ---
    server_upload_group.add_argument(
        "--image-server-pdf-dir", type=str, default="/",
        help="Subdirectory on the server (relative to --image-server-path-prefix) to upload the final PDF to."
    )
    server_upload_group.add_argument(
        "--overwrite-server-file", action="store_true",
        help="If a file with the same name exists on the server, overwrite it. Default is to fail."
    )

    # --- General Options ---
    general_group = parser.add_argument_group('General Options')
    general_group.add_argument("--debug", action="store_true", help="Enable detailed debug messages.")
    general_group.add_argument("--skip-basic-land", action="store_true", help="Skip basic lands.")
    general_group.add_argument("--sort", action="store_true", help="Sort PNGs alphabetically (for directory scan mode or if --png-out-dir copies all from dir).")
    general_group.add_argument("--cameo", action="store_true", help="Use PIL-based PDF generation (modeled after create_pdf.py/utilities.py) when --output-format is pdf. This mode uses fixed layouts from an internal 'layouts.json' equivalent and ignores most page/layout/cut-line options. Currently best supports --paper-type letter or a4 (if in layouts). EXPECTS an 'assets' FOLDER with registration mark images (e.g., 'letter_registration.jpg') next to the script for proper Cameo output.")
    general_group.add_argument("--basic-land-set", type=str, default=None, help="Comma-separated list of set codes to filter basic lands by (e.g., 'lea,unh,neo'). Behavior is controlled by --basic-land-set-mode.")
    general_group.add_argument("--basic-land-set-mode", type=str, default="prefer", choices=["prefer", "force"], help="Controls how --basic-land-set is applied. 'prefer' will use the specified sets if available, but fall back to any set if not. 'force' will fail if no cards from the specified sets are found.")
    general_group.add_argument("--spell-set", type=str, default=None, help="Comma-separated list of set codes to filter non-land cards ('spells') by. Behavior is controlled by --spell-set-mode.")
    general_group.add_argument("--spell-set-mode", type=str, default="prefer", choices=["prefer", "force"], help="Controls how --spell-set is applied. 'prefer' will use the specified sets if available, but fall back to any set if not. 'force' will fail if no cards from the specified sets are found.")

    # --- Page & Layout Options ---
    pg_layout_group = parser.add_argument_group('Page and Layout Options (for PDF/PNG grid output; largely IGNORED by --cameo mode)')
    pg_layout_group.add_argument("--paper-type", type=str, default="letter", choices=["letter", "legal"], help="Conceptual paper type. For ReportLab PDF: Letter 3x3, Legal 3x4. For --cameo PDF: must match a layout like 'letter'.")
    pg_layout_group.add_argument("--page-margin", type=str, default="5mm", help="Margin around the grid (e.g., '5mm', '0.25in', '10px').")
    pg_layout_group.add_argument("--image-spacing-pixels", type=int, default=0, help="Spacing between images in pixels.")
    pg_layout_group.add_argument("--dpi", type=int, default=300, choices=[72, 96, 150, 300, 600], help="DPI for output and interpreting inch/mm dimensions.")
    pg_layout_group.add_argument("--page-bg-color", type=str, default="white", help="Overall page/canvas background color.")
    pg_layout_group.add_argument("--image-cell-bg-color", type=str, default="black", help="Background color directly behind transparent image parts.")
    pg_layout_group.add_argument("--cameo-label-font-size", type=int, default=32, help="[Cameo Mode Only] Font size for the page label. This is a base size in points, which is then scaled by DPI. A reasonable range is 24-48. Must be between 8 and 96.")
    
    # --- Cut Line Options ---
    cut_line_group = parser.add_argument_group('Cut Line Options (for PDF/PNG grid output; IGNORED by --cameo mode)')
    cut_line_group.add_argument( "--cut-lines", action="store_true", help="Enable drawing of cut lines.")
    cut_line_group.add_argument( "--cut-line-length", type=str, default="3mm", help="Length of cut lines (e.g., '3mm', '0.1in', '5px').")
    cut_line_group.add_argument( "--cut-line-color", type=str, default="gray", help="Color of cut lines.")
    cut_line_group.add_argument( "--cut-line-width-pt", type=float, default=0.25, help="Thickness of cut lines in points (for PDF output).")
    cut_line_group.add_argument( "--cut-line-width-px", type=int, default=1, help="Thickness of cut lines in pixels (for PNG output).")

    args = parser.parse_args()

    # --- Mode Validation ---
    if not args.png_dir and not args.image_server_base_url:
        parser.error("Either --png-dir or --image-server-base-url must be specified.")
    if args.png_dir and args.image_server_base_url:
        parser.error("Cannot specify both --png-dir and --image-server-base-url. Choose one source.")
    if args.png_out_dir and not args.deck_list:
        parser.error("--png-out-dir requires --deck-list to be specified.")
    if args.png_out_dir and (args.output_file or args.output_format != "pdf"):
        if args.output_file: print("Warning: --output-file is ignored when --png-out-dir is used.")
        if args.output_format != "pdf": print(f"Warning: --output-format {args.output_format} is ignored when --png-out-dir is used.")
    if args.cameo and args.output_format != "pdf":
        print("Warning: --cameo option is only applicable when --output-format is 'pdf'. Ignoring --cameo."); args.cameo = False
    if not (8 <= args.cameo_label_font_size <= 96):
        parser.error("--cameo-label-font-size must be between 8 and 96.")
    
    if args.upload_to_server:
        if not args.image_server_base_url:
            parser.error("--upload-to-server requires --image-server-base-url.")
        if args.output_format != "pdf":
            parser.error("--upload-to-server is only supported for 'pdf' output format.")
        if args.png_out_dir:
            parser.error("--upload-to-server cannot be used with --png-out-dir.")

    # --- Initial Validations ---
    if args.png_dir and not os.path.isdir(args.png_dir):
        print(f"Error: PNG directory '{args.png_dir}' not found."); return
    if args.deck_list and not os.path.isfile(args.deck_list):
        print(f"Error: Deck list file '{args.deck_list}' not found."); return
    try:
        validated_paper_type = parse_paper_type(args.paper_type)
    except ValueError as e:
        print(f"Error: {e}"); return

    parsed_basic_land_sets: Optional[List[str]] = None
    if args.basic_land_set:
        parsed_basic_land_sets = [s.strip().lower() for s in args.basic_land_set.split(',') if s.strip()]
        if args.debug and parsed_basic_land_sets:
            print(f"DEBUG: Parsed basic land set filter: {parsed_basic_land_sets}")

    parsed_spell_sets: Optional[List[str]] = None
    if args.spell_set:
        parsed_spell_sets = [s.strip().lower() for s in args.spell_set.split(',') if s.strip()]
        if args.debug and parsed_spell_sets:
            print(f"DEBUG: Parsed spell set filter: {parsed_spell_sets}")

    # --- Discover images from source ---
    print("--- Discovering Images ---")
    png_source_path_on_server = "/"
    if args.image_server_base_url:
        print(f"Using web server: {args.image_server_base_url}")
        # --- MODIFIED: Construct the full path for fetching PNGs ---
        # Cleanly join path components, removing extra slashes and handling empty parts.
        png_path_parts = [p.strip('/') for p in [args.image_server_path_prefix, args.image_server_png_dir] if p.strip('/')]
        png_source_path_on_server = '/' + '/'.join(png_path_parts)
    else:
        print(f"Using local directory: {args.png_dir}")
    
    # Pass the fully constructed path to the discovery function.
    all_cards_map = discover_images(
        png_dir=args.png_dir,
        image_server_base_url=args.image_server_base_url,
        image_server_path_prefix=png_source_path_on_server,
        debug=args.debug
    )
    if not all_cards_map:
        print("No images found in source. Exiting."); return

    # --- Determine list of images to process ---
    image_sources_to_process: List[ImageSource] = []
    missing_cards_from_deck: List[str] = []
    try:
        if args.deck_list:
            print("\n--- Deck List Mode ---")
            image_sources_to_process, missing_cards_from_deck = process_deck_list(
                args.deck_list, all_cards_map,
                args.skip_basic_land, 
                parsed_basic_land_sets, args.basic_land_set_mode,
                parsed_spell_sets, args.spell_set_mode,
                args.debug
            )
            if missing_cards_from_deck:
                write_missing_cards_file(args.deck_list, missing_cards_from_deck)
            if not image_sources_to_process and not args.png_out_dir:
                print("No images to print (after potential skips). Exiting."); return
            if image_sources_to_process:
                print(f"Prepared {len(image_sources_to_process)} image instances (excluding any skipped basic lands).")
        
        elif not args.png_out_dir:
            print("\n--- Directory Scan Mode (for PDF/PNG grid) ---")
            skipped_basics_count = 0
            all_available_sources = [source for source_list in all_cards_map.values() for source in source_list]
            if args.skip_basic_land:
                non_basic_sources = []
                for source in all_available_sources:
                    basename = os.path.splitext(os.path.basename(urllib.parse.unquote(source.original)))[0]
                    norm_name = normalize_card_name(basename)
                    if norm_name in BASIC_LAND_NAMES: skipped_basics_count += 1
                    else: non_basic_sources.append(source)
                image_sources_to_process = non_basic_sources
            else:
                image_sources_to_process = all_available_sources
            if args.skip_basic_land and skipped_basics_count > 0:
                print(f"  Skipped {skipped_basics_count} basic land files.")
            if not image_sources_to_process:
                print(f"No suitable PNGs found. Exiting."); return
            if args.sort:
                image_sources_to_process.sort(key=lambda x: x.original)
            print(f"Found {len(image_sources_to_process)} total PNGs ({'sorted' if args.sort else 'unsorted'}).")
        
        elif args.png_out_dir and not args.deck_list:
            print("Error: --png-out-dir specified without a --deck-list. Nothing to do."); return

        # --- Perform Action: Copy PNGs or Generate Grid ---
        if args.png_out_dir:
            if not args.deck_list:
                print("Critical Error: --png-out-dir mode reached without a deck list. Please report this bug."); return
            if image_sources_to_process:
                copy_deck_pngs(image_sources_to_process, args.png_out_dir, args.debug)
            elif not missing_cards_from_deck:
                print("No images to copy (deck list may have contained only skipped basic lands or was empty).")
        else:
            if not image_sources_to_process:
                print("No images to generate grid output. Exiting."); return
            
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
                output_pdf_filename = f"{os.path.basename(base_output_filename_final)}.pdf"
                pdf_buffer = None
                if args.upload_to_server:
                    pdf_buffer = io.BytesIO()
                    output_target = pdf_buffer
                else:
                    output_target = f"{base_output_filename_final}.pdf"
                
                if args.cameo:
                    create_pdf_cameo_style(image_sources=image_sources_to_process, output_path_or_buffer=output_target, paper_type_arg=validated_paper_type, target_dpi=args.dpi, image_cell_bg_color_str=args.image_cell_bg_color, pdf_name_label=name_for_pdf_label, label_font_size_base=args.cameo_label_font_size, debug=args.debug)
                else:
                    create_pdf_grid(image_sources=image_sources_to_process, output_path_or_buffer=output_target, paper_type_str=validated_paper_type, image_spacing_pixels=args.image_spacing_pixels, dpi=args.dpi, page_margin_str=args.page_margin, page_background_color_str=args.page_bg_color, image_cell_background_color_str=args.image_cell_bg_color, cut_lines=args.cut_lines, cut_line_length_str=args.cut_line_length, cut_line_color_str=args.cut_line_color, cut_line_width_pt=args.cut_line_width_pt, debug=args.debug)
                
                if args.upload_to_server and pdf_buffer:
                    print("\n--- Uploading PDF to Server ---")
                    # --- MODIFIED: Construct the full upload URL ---
                    # Join the base prefix, the relative PDF directory, and the filename.
                    pdf_path_parts = [p.strip('/') for p in [args.image_server_path_prefix, args.image_server_pdf_dir, output_pdf_filename] if p.strip('/')]
                    full_path_for_upload = '/' + '/'.join(pdf_path_parts)
                    
                    # Combine the base URL with the full path.
                    upload_url = f"{args.image_server_base_url.rstrip('/')}{full_path_for_upload}"

                    if not args.overwrite_server_file:
                        if check_server_file_exists(upload_url, args.debug):
                            print(f"Error: File already exists at {upload_url}.")
                            print("Use --overwrite-server-file to replace it.")
                            return
                    
                    pdf_bytes = pdf_buffer.getvalue()
                    upload_file_to_server(upload_url, pdf_bytes, 'application/pdf', args.debug)

            elif args.output_format == "png":
                create_png_output(image_files=image_sources_to_process, base_output_filename=base_output_filename_final, paper_type_str=validated_paper_type, dpi=args.dpi, image_spacing_pixels=args.image_spacing_pixels, page_margin_str=args.page_margin, page_background_color_str=args.page_bg_color, image_cell_background_color_str=args.image_cell_bg_color, cut_lines=args.cut_lines, cut_line_length_str=args.cut_line_length, cut_line_color_str=args.cut_line_color, cut_line_width_px=args.cut_line_width_px, debug=args.debug)
            else:
                print(f"Error: Unknown output format '{args.output_format}'.")
    finally:
        cleanup_temp_files()
        for img_source in image_sources_to_process:
            img_source.cleanup()

if __name__ == "__main__":
    main()

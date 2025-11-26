"""
Output utilities for MtgPng2Pdf.
"""

import os
import shutil
import urllib.parse
from collections import defaultdict
from typing import List, Dict, Union

from image_handler import ImageSource

def print_selection_manifest(manifest: Dict[str, Dict[str, Dict[str, int]]]):
    """Prints a formatted summary of which card versions were selected."""
    if not manifest:
        return
        
    print("\n--- Card Selection Manifest ---")
    
    for section_name in ["Deck", "Sideboard", "Token"]:
        if section_name in manifest and manifest[section_name]:
            print(f"\n{section_name}:")
            # Sort by original card name
            for card_name in sorted(manifest[section_name].keys()):
                versions = manifest[section_name][card_name]
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

import io
import math
import os
from PIL import Image, ImageDraw, ImageFont

from parsing_utils import parse_dimension_to_pixels
from config import TARGET_IMG_WIDTH_INCHES, TARGET_IMG_HEIGHT_INCHES

from typing import List, Dict, Union, Optional

from config import LAYOUTS_DATA, CameoPaperSize, CameoCardSize, TARGET_IMG_WIDTH_INCHES, TARGET_IMG_HEIGHT_INCHES
from image_handler import ImageSource
from pdf_generator import draw_card_layout_cameo, calculate_max_print_bleed_cameo

from web_utils import check_server_file_exists, upload_file_to_server

def create_png_output(image_sources: List[ImageSource], output_path_or_buffer: Union[str, io.BytesIO], **kwargs):
    print(f"\n--- PNG Page Generation (PIL-based) ---")
    
    upload_to_server = kwargs.get("upload_to_server", False)
    if upload_to_server:
        print(f"Output target: Server upload")
    elif isinstance(output_path_or_buffer, str):
        print(f"Output file: {output_path_or_buffer}")

    paper_type_arg = kwargs.get("paper_type_str")
    target_dpi = kwargs.get("dpi", 300)
    image_cell_bg_color_str = kwargs.get("image_cell_background_color_str", "black")
    pdf_name_label = kwargs.get("pdf_name_label")
    label_font_size_base = kwargs.get("cameo_label_font_size", 32)
    debug = kwargs.get("debug", False)

    if paper_type_arg.lower() == "letter": cameo_paper_key = CameoPaperSize.LETTER
    elif paper_type_arg.lower() == "a4": cameo_paper_key = CameoPaperSize.A4
    else: print(f"Error: --cameo PNG generation: Paper type '{paper_type_arg}' is not directly supported by embedded cameo layouts."); return
    
    cameo_card_key = CameoCardSize.STANDARD
    try: paper_layout_config = LAYOUTS_DATA["paper_layouts"][cameo_paper_key]; card_layout_config = paper_layout_config["card_layouts"][cameo_card_key]
    except KeyError: print(f"Error: Layout for paper '{cameo_paper_key}' and card size '{cameo_card_key}' not found."); return

    num_rows = len(card_layout_config["y_pos"]); num_cols = len(card_layout_config["x_pos"]); num_cards_per_page = num_rows * num_cols
    layout_base_ppi = 300.0; ppi_ratio = target_dpi / layout_base_ppi
    page_width_px_scaled = math.floor(paper_layout_config["width"] * ppi_ratio); page_height_px_scaled = math.floor(paper_layout_config["height"] * ppi_ratio)
    card_slot_width_layout = card_layout_config["width"]; card_slot_height_layout = card_layout_config["height"]
    crop_percentage_on_source = 0.0; extend_corners_on_source_px = 0
    max_print_bleed_layout_units = calculate_max_print_bleed_cameo(card_layout_config["x_pos"], card_layout_config["y_pos"], card_slot_width_layout, card_slot_height_layout)

    script_dir = os.path.dirname(os.path.abspath(__file__)); asset_dir_cameo = os.path.join(script_dir, "assets"); registration_filename = f'{cameo_paper_key}_registration.jpg'; registration_path = os.path.join(asset_dir_cameo, registration_filename)
    master_page_background: Optional[Image.Image] = None
    if os.path.exists(registration_path):
        try:
            reg_im_original = Image.open(registration_path); reg_im_scaled = reg_im_original.resize((page_width_px_scaled, page_height_px_scaled))
            if reg_im_scaled.mode != 'RGB': reg_im_scaled = reg_im_scaled.convert('RGB')
            master_page_background = reg_im_scaled
        except Exception as e_reg: print(f"  Warning: Could not load registration image: {e_reg}")
    if master_page_background is None: master_page_background = Image.new("RGB", (page_width_px_scaled, page_height_px_scaled), "white")

    pil_cell_bg_color: Union[str, Tuple[int,int,int], None] = image_cell_bg_color_str
    total_images_to_process = len(image_sources)

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

        page_num_for_label = (page_start_index // num_cards_per_page) + 1
        template_name = card_layout_config.get("template", "unknown_template")
        base_label_part = f"template: {template_name}, sheet: {page_num_for_label}"
        if pdf_name_label: label_text = f"name: {pdf_name_label}, {base_label_part}"
        else: label_text = base_label_part

        try:
            draw_page_text = ImageDraw.Draw(current_page_pil_image)
            text_x_pos = math.floor((paper_layout_config["width"] - 180) * ppi_ratio); text_y_pos = math.floor((paper_layout_config["height"] - 180) * ppi_ratio)
            font_size_scaled = math.floor(label_font_size_base * ppi_ratio)
            page_font = None
            try: 
                script_dir = os.path.dirname(os.path.abspath(__file__)); font_path = os.path.join(script_dir, "assets", "DejaVuSans.ttf"); page_font = ImageFont.truetype(font_path, size=font_size_scaled)
            except IOError: print("  Warning: Font 'assets/DejaVuSans.ttf' not found.");
            except Exception: pass
            if page_font: draw_page_text.text((text_x_pos, text_y_pos), label_text, fill=(0,0,0), anchor="ra", font=page_font)
        except Exception as e_font:
            if debug: print(f"DEBUG CAMEO: Could not draw page label: {e_font}")

        if upload_to_server:
            base, _ = os.path.splitext(output_path_or_buffer)
            page_filename = f"{base}-{page_num_for_label}.png"
            
            png_buffer = io.BytesIO()
            current_page_pil_image.save(png_buffer, format='PNG', compress_level=6)
            png_bytes = png_buffer.getvalue()

            image_server_base_url = kwargs.get("image_server_base_url")
            image_server_path_prefix = kwargs.get("image_server_path_prefix")
            image_server_deck_dir = kwargs.get("image_server_deck_dir")
            overwrite_server_file = kwargs.get("overwrite_server_file")

            png_path_parts = [p.strip('/') for p in [image_server_path_prefix, image_server_deck_dir, page_filename] if p.strip('/')]
            full_path_for_upload = '/' + '/'.join(png_path_parts)
            upload_url = f"{image_server_base_url.rstrip('/')}{full_path_for_upload}"

            if not overwrite_server_file:
                if check_server_file_exists(upload_url, debug):
                    print(f"Error: File already exists at {upload_url}.")
                    print("Use --overwrite-server-file to replace it.")
                    continue
            
            upload_file_to_server(upload_url, png_bytes, 'image/png', debug)
        else:
            base, ext = os.path.splitext(output_path_or_buffer)
            page_filename = f"{base}-{page_num_for_label}{ext}"
            current_page_pil_image.save(page_filename, format='PNG', compress_level=6)
            print(f"PNG page {page_num_for_label} saved to {page_filename}")

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

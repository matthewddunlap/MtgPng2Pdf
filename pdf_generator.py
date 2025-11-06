"""
PDF generation for MtgPng2Pdf.
"""

import io
import math
import os
from typing import List, Union, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors as reportlab_colors
from reportlab.lib.pagesizes import letter, legal
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from config import LAYOUTS_DATA, CameoPaperSize, CameoCardSize, TARGET_IMG_WIDTH_INCHES, TARGET_IMG_HEIGHT_INCHES, PAPER_SIZES_PT
from image_handler import ImageSource
from parsing_utils import parse_dimension_to_pixels

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

def create_pdf_cameo_style(image_sources: List[ImageSource], output_path_or_buffer: Union[str, io.BytesIO], paper_type_arg: str, target_dpi: int, image_cell_bg_color_str: str, pdf_name_label: Optional[str], label_font_size_base: int, pdf_quality: int, debug: bool = False):
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
    crop_percentage_on_source = 0.0; extend_corners_on_source_px = 0
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
        all_pil_pages[0].save(output_path_or_buffer, format='PDF', save_all=True, append_images=all_pil_pages[1:], resolution=float(target_dpi), quality=pdf_quality)
        if isinstance(output_path_or_buffer, str): print(f"Cameo PDF generation successful: {output_path_or_buffer} ({len(all_pil_pages)} page(s))")
        else: print(f"Cameo PDF generation to memory buffer successful ({len(all_pil_pages)} page(s))")
    except Exception as e: print(f"Error saving Cameo PDF: {e}")

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

"""
Main logic for MtgPng2Pdf.
"""

import argparse
import io
import os
from typing import List, Optional

from card_processing import process_deck_list
from config import BASIC_LAND_NAMES
from image_handler import discover_images, ImageSource
from output_utils import write_missing_cards_file, print_selection_manifest, copy_deck_pngs, create_png_output
from parsing_utils import parse_paper_type, normalize_card_name
from pdf_generator import create_pdf_cameo_style, create_pdf_grid
from web_utils import check_server_file_exists, upload_file_to_server, cleanup_temp_files

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
        "--image-server-deck-dir", type=str, default="/",
        help="Subdirectory on the server (relative to --image-server-path-prefix) to upload the final PDF or PNG to."
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
    general_group.add_argument("--basic-land-set-mode", type=str, default="prefer", choices=["prefer", "force", "minimum"], help="Controls how --basic-land-set is applied. 'prefer' will use the specified sets if available, but fall back to any set if not. 'force' will fail if no cards from the specified sets are found. 'minimum' will use at least one from the specified sets and fallback for the rest.")
    general_group.add_argument("--spell-set", type=str, default=None, help="Comma-separated list of set codes to filter non-land cards ('spells') by. Behavior is controlled by --spell-set-mode.")
    general_group.add_argument("--spell-set-mode", type=str, default="prefer", choices=["prefer", "force", "minimum"], help="Controls how --spell-set is applied. 'prefer' will use the specified sets if available, but fall back to any set if not. 'force' will fail if no cards from the specified sets are found. 'minimum' will use at least one from the specified sets and fallback for the rest.")
    general_group.add_argument("--basic-land-set-exclude", type=str, default=None, help="Comma-separated list of set codes to EXCLUDE for basic lands (e.g., 'unh,ust').")
    general_group.add_argument("--spell-set-exclude", type=str, default=None, help="Comma-separated list of set codes to EXCLUDE for non-land cards ('spells').")
    general_group.add_argument("--card-set", type=str, action="append", help="Override spell-set for a specific card. Format: \"<Card Name>:<Set(s)>[:<Mode>]\". Can be used multiple times.")

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

    parsed_basic_land_sets_exclude: Optional[List[str]] = None
    if args.basic_land_set_exclude:
        parsed_basic_land_sets_exclude = [s.strip().lower() for s in args.basic_land_set_exclude.split(',') if s.strip()]
        if args.debug and parsed_basic_land_sets_exclude:
            print(f"DEBUG: Parsed basic land set exclusion filter: {parsed_basic_land_sets_exclude}")

    parsed_spell_sets_exclude: Optional[List[str]] = None
    if args.spell_set_exclude:
        parsed_spell_sets_exclude = [s.strip().lower() for s in args.spell_set_exclude.split(',') if s.strip()]
        if args.debug and parsed_spell_sets_exclude:
            print(f"DEBUG: Parsed spell set exclusion filter: {parsed_spell_sets_exclude}")

    card_set_overrides = {}
    if args.card_set:
        for override in args.card_set:
            parts = override.split(':')
            if len(parts) < 2 or len(parts) > 3:
                parser.error(f"Invalid --card-set format: {override}")
            card_name = normalize_card_name(parts[0])
            sets = [s.strip().lower() for s in parts[1].split(',') if s.strip()]
            mode = args.spell_set_mode
            if len(parts) == 3:
                mode = parts[2].lower()
                if mode not in ["prefer", "force", "minimum"]:
                    parser.error(f"Invalid mode in --card-set: {mode}")
            card_set_overrides[card_name] = {"sets": sets, "mode": mode}

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
            image_sources_to_process, missing_cards_from_deck, selection_manifest = process_deck_list(
                args.deck_list, all_cards_map,
                args.skip_basic_land, 
                parsed_basic_land_sets, args.basic_land_set_mode,
                parsed_spell_sets, args.spell_set_mode,
                parsed_basic_land_sets_exclude,
                parsed_spell_sets_exclude,
                card_set_overrides,
                args.debug
            )
            
            if missing_cards_from_deck:
                write_missing_cards_file(args.deck_list, missing_cards_from_deck)

            if selection_manifest:
                print_selection_manifest(selection_manifest)

            if not image_sources_to_process and not args.png_out_dir:
                print("No images to print (after potential skips). Exiting."); return
            if image_sources_to_process:
                print(f"Prepared {len(image_sources_to_process)} image instances (excluding any skipped basic lands).")
        
        elif not args.png_out_dir:
            print("\n--- Directory Scan Mode (for PDF/PNG grid) ---")
            skipped_basics_count = 0
            all_available_sources = [source for source_list in all_cards_map.values() for source in source_list]
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
                    pdf_path_parts = [p.strip('/') for p in [args.image_server_path_prefix, args.image_server_deck_dir, output_pdf_filename] if p.strip('/')]
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
                if args.upload_to_server:
                    # We will generate multiple pages in memory and upload them sequentially
                    base_output_filename = os.path.basename(base_output_filename_final)
                    create_png_output(image_sources=image_sources_to_process, output_path_or_buffer=base_output_filename, paper_type_str=validated_paper_type, dpi=args.dpi, image_spacing_pixels=args.image_spacing_pixels, page_margin_str=args.page_margin, page_background_color_str=args.page_bg_color, image_cell_background_color_str=args.image_cell_bg_color, cut_lines=args.cut_lines, cut_line_length_str=args.cut_line_length, cut_line_color_str=args.cut_line_color, cut_line_width_px=args.cut_line_width_px, pdf_name_label=name_for_pdf_label, cameo_label_font_size=args.cameo_label_font_size, debug=args.debug, upload_to_server=True, image_server_base_url=args.image_server_base_url, image_server_path_prefix=args.image_server_path_prefix, image_server_deck_dir=args.image_server_deck_dir, overwrite_server_file=args.overwrite_server_file)
                else:
                    output_target = f"{base_output_filename_final}.png"
                    create_png_output(image_sources=image_sources_to_process, output_path_or_buffer=output_target, paper_type_str=validated_paper_type, dpi=args.dpi, image_spacing_pixels=args.image_spacing_pixels, page_margin_str=args.page_margin, page_background_color_str=args.page_bg_color, image_cell_background_color_str=args.image_cell_bg_color, cut_lines=args.cut_lines, cut_line_length_str=args.cut_line_length, cut_line_color_str=args.cut_line_color, cut_line_width_px=args.cut_line_width_px, pdf_name_label=name_for_pdf_label, cameo_label_font_size=args.cameo_label_font_size, debug=args.debug)
            else:
                print(f"Error: Unknown output format '{args.output_format}'.")
    finally:
        cleanup_temp_files()
        for img_source in image_sources_to_process:
            img_source.cleanup()
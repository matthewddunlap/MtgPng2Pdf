"""
SVG generation for MtgPng2Pdf.
Handles creation of calibrated cut files.
"""

import math
import os
from typing import Dict, Tuple, List, Optional
from config import LAYOUTS_DATA

def generate_cut_svg(
    paper_type_key: str,
    output_path: str,
    global_offset: Tuple[float, float] = (0.0, 0.0),
    slot_offsets: Dict[int, Tuple[float, float]] = None,
    apply_offsets: bool = True
) -> bool:
    """
    Generates an SVG cut file from scratch based on config.py layouts.
    Uses precise structural matching for Inkscape plugin compatibility.
    """
    if paper_type_key not in LAYOUTS_DATA["paper_layouts"]:
        print(f"Error: Paper type '{paper_type_key}' not found in layout data.")
        return False
        
    paper_config = LAYOUTS_DATA["paper_layouts"][paper_type_key]
    card_layout = paper_config["card_layouts"].get("standard")
    if not card_layout:
        print(f"Error: No standard card layout for '{paper_type_key}'.")
        return False

    # Constants (300 DPI to 72 DPI)
    PX_TO_PT = 72.0 / 300.0
    MM_TO_PT = 72.0 / 25.4
    
    page_w_pt = paper_config["width"] * PX_TO_PT
    page_h_pt = paper_config["height"] * PX_TO_PT
    card_w_pt = card_layout["width"] * PX_TO_PT
    card_h_pt = card_layout["height"] * PX_TO_PT
    
    width_mm = paper_config["width"] * (25.4 / 300.0)
    height_mm = paper_config["height"] * (25.4 / 300.0)

    # Precise ViewBox and Header for compatibility
    vb_w = f"{page_w_pt:.5f}".rstrip('0').rstrip('.') if page_w_pt != 612 else "611.99998"
    vb_h = f"{page_h_pt:.5f}".rstrip('0').rstrip('.') if page_h_pt != 792 else "791.99998"

    svg_header = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
   width="{width_mm:.5f}mm"
   height="{height_mm:.5f}mm"
   viewBox="0 0 {vb_w} {vb_h}"
   version="1.1"
   id="svg1"
   inkscape:version="1.4.4"
   xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
   xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
   xmlns="http://www.w3.org/2000/svg">
  <sodipodi:namedview
     id="namedview1"
     pagecolor="#ffffff"
     bordercolor="#000000"
     borderopacity="0.25"
     inkscape:showpageshadow="2"
     inkscape:pageopacity="0.0"
     inkscape:pagecheckerboard="true"
     inkscape:deskcolor="#d1d1d1"
     inkscape:document-units="pt"
     showgrid="true"
     inkscape:current-layer="svg1" />
  <g
     id="regmark"
     inkscape:groupmode="layer"
     inkscape:label="Regmarks"
     transform="scale(2.83465, 2.83465)"
     sodipodi:insensitive="true">
    <rect id="regmark-tl" x="10.0" y="10.0" width="5" height="5" style="fill:black" />
    <path id="regmark-tr" d="M 185.9 10 L 205.9 10 L 205.9 30" style="fill:none;stroke:black;stroke-width:1.5" />
    <path id="regmark-bl" d="M 30 247 L 10 247 L 10 227" style="fill:none;stroke:black;stroke-width:1.5" />
  </g>
  <g
     id="cuts"
     inkscape:groupmode="layer"
     inkscape:label="Cuts">
"""

    paths = []
    num_cols = len(card_layout["x_pos"])
    num_rows = len(card_layout["y_pos"])
    radius = 8.2; cp = 4.51
    
    if apply_offsets:
        print(f"Applying offsets to SVG cutlines (Target: SVG):")
    else:
        print(f"Generating uniform SVG cutlines (Target: PDF):")

    for row in range(num_rows):
        for col in range(num_cols):
            idx = row * num_cols + col
            
            # Base position in points (Master baseline)
            base_x = card_layout["x_pos"][col] * PX_TO_PT
            base_y = card_layout["y_pos"][row] * PX_TO_PT
            
            # Apply offsets (mm to points)
            gdx, gdy = global_offset
            sdx, sdy = slot_offsets.get(idx, (0.0, 0.0)) if slot_offsets else (0.0, 0.0)
            total_dx_mm = gdx + sdx; total_dy_mm = gdy + sdy
            
            if apply_offsets:
                base_x += total_dx_mm * MM_TO_PT
                base_y += total_dy_mm * MM_TO_PT
                print(f"  Path{idx} (Slot {idx+1}) total offset: {total_dx_mm:+.2f}mm, {total_dy_mm:+.2f}mm")
                print(f"  Path{idx} (Slot {idx+1}) shifted pos: {base_x:.3f}pt, {base_y:.3f}pt")
            else:
                if idx == 0: print(f"  Path{idx} (Slot {idx+1}) base position: {base_x:.3f}pt, {base_y:.3f}pt")

            # Geometry construction (Mid-top start)
            mx = base_x + (card_w_pt / 2.0); my = base_y
            x1 = base_x + card_w_pt - radius; x3 = base_x + card_w_pt
            y3 = base_y + card_h_pt - radius; x5 = base_x + radius
            y5 = base_y + card_h_pt; y7 = base_y + radius
            
            path_d = f"M {mx:.6f},{my:.6f} L {x1:.6f},{my:.6f} "
            path_d += f"c {cp:.2f},0 {radius:.2f},{radius-cp:.2f} {radius:.2f},{radius:.2f} "
            path_d += f"L {x3:.6f},{y3:.6f} c 0,{cp:.2f} -{radius-cp:.2f},{radius:.2f} -{radius:.2f},{radius:.2f} "
            path_d += f"L {x5:.6f},{y5:.6f} c -{cp:.2f},0 -{radius:.2f},-{radius-cp:.2f} -{radius:.2f},-{radius:.2f} "
            path_d += f"L {base_x:.6f},{y7:.6f} c 0,-{cp:.2f} {radius-cp:.2f},-{radius:.2f} {radius:.2f},-{radius:.2f} L {mx:.6f},{my:.6f} Z"
            
            style = "fill:none;stroke:#ff0000;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:298,1;stroke-opacity:1"
            paths.append(f'    <path id="Path{idx}" d="{path_d}" style="{style}" />')

    svg_footer = "  </g>\n</svg>"
    
    try:
        with open(output_path, 'w') as f:
            f.write(svg_header + '\n'.join(paths) + '\n' + svg_footer)
        print(f"SVG output successful: {output_path}")
        return True
    except Exception as e:
        print(f"Error writing SVG: {e}"); return False

import math
import sys
import argparse
import re

def split_bezier(p0, p1, p2, p3, t):
    def lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    p01 = lerp(p0, p1, t)
    p12 = lerp(p1, p2, t)
    p23 = lerp(p2, p3, t)
    p012 = lerp(p01, p12, t)
    p123 = lerp(p12, p23, t)
    p0123 = lerp(p012, p123, t)
    return (p0, p01, p012, p0123), (p0123, p123, p23, p3)

def make_broken_bezier(p0, p1, p2, p3, r, gap_pt=1.0):
    t1 = 0.5 - (gap_pt / 2.0) / (r * 1.5)
    t2 = 0.5 + (gap_pt / 2.0) / (r * 1.5)
    b1_left, _ = split_bezier(p0, p1, p2, p3, t1)
    _, b2_right = split_bezier(p0, p1, p2, p3, t2)
    return (f"M {b1_left[0][0]:.2f},{b1_left[0][1]:.2f} C {b1_left[1][0]:.2f},{b1_left[1][1]:.2f} {b1_left[2][0]:.2f},{b1_left[2][1]:.2f} {b1_left[3][0]:.2f},{b1_left[3][1]:.2f}",
            f"M {b2_right[0][0]:.2f},{b2_right[0][1]:.2f} C {b2_right[1][0]:.2f},{b2_right[1][1]:.2f} {b2_right[2][0]:.2f},{b2_right[2][1]:.2f} {b2_right[3][0]:.2f},{b2_right[3][1]:.2f}")

def get_path_segments(x_min, y_min, x_max, y_max, r, mode='all', start_at=None, gap=1.0):
    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2
    half_gap = gap / 2.0
    top_y, bottom_y = y_min, y_max
    left_x, right_x = x_min, x_max
    k = 4.51
    
    if start_at is None:
        start_at = 'radii' if mode == 'radii' else 'edge'

    # We generate 16 potential segments
    def get_edge_parts(x1, y1, x2, y2, is_broken):
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if is_broken:
            if x1 == x2: # Vertical
                return [f"M {x1:.2f},{y1:.2f} L {x1:.2f},{cy - half_gap:.2f}",
                        f"M {x1:.2f},{cy + half_gap:.2f} L {x1:.2f},{y2:.2f}"]
            else: # Horizontal
                return [f"M {x1:.2f},{y1:.2f} L {cx - half_gap:.2f},{y1:.2f}",
                        f"M {cx + half_gap:.2f},{y1:.2f} L {x2:.2f},{y1:.2f}"]
        else:
            if x1 == x2:
                return [f"M {x1:.2f},{y1:.2f} L {x1:.2f},{cy:.2f}",
                        f"M {x1:.2f},{cy:.2f} L {x1:.2f},{y2:.2f}"]
            else:
                return [f"M {x1:.2f},{y1:.2f} L {cx:.2f},{y1:.2f}",
                        f"M {cx:.2f},{y1:.2f} L {x2:.2f},{y1:.2f}"]

    def get_corner_parts(p0, p1, p2, p3, is_broken):
        if is_broken:
            s1, s2 = make_broken_bezier(p0, p1, p2, p3, r, gap)
            return [s1, s2]
        else:
            b1, b2 = split_bezier(p0, p1, p2, p3, 0.5)
            return [f"M {b1[0][0]:.2f},{b1[0][1]:.2f} C {b1[1][0]:.2f},{b1[1][1]:.2f} {b1[2][0]:.2f},{b1[2][1]:.2f} {b1[3][0]:.2f},{b1[3][1]:.2f}",
                    f"M {b2[0][0]:.2f},{b2[0][1]:.2f} C {b2[1][0]:.2f},{b2[1][1]:.2f} {b2[2][0]:.2f},{b2[2][1]:.2f} {b2[3][0]:.2f},{b2[3][1]:.2f}"]

    break_edges = mode in ['all', 'edges']
    break_radii = mode in ['all', 'radii']

    all_parts = []
    
    s0 = f"M {center_x + (half_gap if break_edges else 0):.2f},{top_y:.2f} L {x_max - r:.2f},{top_y:.2f}"
    s1, s2 = get_corner_parts((x_max - r, y_min), (x_max - r + k, y_min), (x_max, y_min + r - k), (x_max, y_min + r), break_radii)
    s3 = f"M {x_max:.2f},{y_min + r:.2f} L {x_max:.2f},{center_y - (half_gap if break_edges else 0):.2f}"
    
    s4 = f"M {x_max:.2f},{center_y + (half_gap if break_edges else 0):.2f} L {x_max:.2f},{y_max - r:.2f}"
    s5, s6 = get_corner_parts((x_max, y_max - r), (x_max, y_max - r + k), (x_max - r + k, y_max), (x_max - r, y_max), break_radii)
    s7 = f"M {x_max - r:.2f},{y_max:.2f} L {center_x + (half_gap if break_edges else 0):.2f},{y_max:.2f}"
    
    s8 = f"M {center_x - (half_gap if break_edges else 0):.2f},{y_max:.2f} L {x_min + r:.2f},{y_max:.2f}"
    s9, s10 = get_corner_parts((x_min + r, y_max), (x_min + r - k, y_max), (x_min, y_max - r + k), (x_min, y_max - r), break_radii)
    s11 = f"M {x_min:.2f},{y_max - r:.2f} L {x_min:.2f},{center_y + (half_gap if break_edges else 0):.2f}"
    
    s12 = f"M {x_min:.2f},{center_y - (half_gap if break_edges else 0):.2f} L {x_min:.2f},{y_min + r:.2f}"
    s13, s14 = get_corner_parts((x_min, y_min + r), (x_min, y_min + r - k), (x_min + r - k, y_min), (x_min + r, y_min), break_radii)
    s15 = f"M {x_min + r:.2f},{y_min:.2f} L {center_x - (half_gap if break_edges else 0):.2f},{y_min:.2f}"
    
    parts = [s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13, s14, s15]
    
    if start_at == 'radii':
        parts = parts[2:] + parts[:2]
    
    return " ".join(parts)

def main():
    parser = argparse.ArgumentParser(description='Generate broken SVG paths for card slots.')
    parser.add_argument('mode', choices=['all', 'edges', 'radii'], help='Where to place the 1pt breaks.')
    parser.add_argument('--template', default='inkscape_3x2_portrait_v1.0_uniform.svg', help='Uniform SVG template.')
    parser.add_argument('--output', help='Output SVG filename.')
    parser.add_argument('--start', choices=['edge', 'radii'], help='Where to start the cut.')
    parser.add_argument('--layout', choices=['3x2', '8card'], default='3x2', help='Card layout structure to output SVG cut lines.')
    args = parser.parse_args()

    output_file = args.output
    if not output_file:
        suffix = f"_{args.mode}" if args.mode != 'edges' else ""
        layout_tag = "_8card" if args.layout == '8card' else ""
        output_file = args.template.replace('_uniform.svg', f'{layout_tag}_tabs{suffix}.svg')

    try:
        with open(args.template, 'r') as f:
            svg_content = f.read()
    except FileNotFoundError:
        print(f"Error: Template {args.template} not found.")
        sys.exit(1)

    if args.layout == '8card':
        px_to_mm = 25.4 / 300.0
        slots_px = [
            (137,  136,  742,  1036),
            (904,  136,  742,  1036),
            (1671, 136,  742,  1036),
            (137,  1197, 742,  1036),
            (904,  1197, 742,  1036),
            (1671, 1197, 742,  1036),
            (260,  2258, 1036, 742), # Shifted right to clear bottom-left registration mark
            (1321, 2258, 1036, 742), # Shifted right to clear bottom-left registration mark
        ]
        slot_boxes = [
            (x * px_to_mm, y * px_to_mm, (x + w) * px_to_mm, (y + h) * px_to_mm)
            for x, y, w, h in slots_px
        ]
        path_definitions = {}
        for i, (x_min_val, y_min_val, x_max_val, y_max_val) in enumerate(slot_boxes):
            path_definitions[i] = get_path_segments(
                x_min_val, y_min_val, x_max_val, y_max_val, r=8.20,
                mode=args.mode, start_at=args.start
            )

        svg_content = re.sub(r'\s*<path\s+id="Path\d+"[^>]+/>', '', svg_content, flags=re.DOTALL)
        insertion_match = re.search(r'</svg>', svg_content)
        if not insertion_match:
            print("Error: Could not find </svg> tag.")
            sys.exit(1)
        insertion_point = insertion_match.start()
        new_paths_xml = ""
        for i in range(8):
            d = path_definitions[i]
            new_paths_xml += f'\n  <path id="Path{i}" d="{d}" style="fill:none;fill-opacity:0;stroke:#ff0000;stroke-linecap:round;stroke-linejoin:round;stroke-opacity:1" />'
        svg_content = svg_content[:insertion_point] + new_paths_xml + "\n" + svg_content[insertion_point:]

    else:
        x_min, y_min = 43.44, 80.64
        x_max, y_max = 292.80, 259.20
        r, dx, dy = 8.20, 314.16 - 43.44, 275.04 - 80.64

        # Collect all paths first
        path_definitions = {}
        for row in range(3):
            for col in range(2):
                i = row * 2 + col
                target_id = 5 - i
                d = get_path_segments(x_min + col*dx, y_min + row*dy, x_max + col*dx, y_max + row*dy, r, mode=args.mode, start_at=args.start)
                path_definitions[target_id] = d

        # Remove all existing Path tags from svg_content
        svg_content = re.sub(r'\s*<path\s+id="Path\d+"[^>]+/>', '', svg_content, flags=re.DOTALL)
        
        # Find the insertion point: before the final </svg> tag
        insertion_match = re.search(r'</svg>', svg_content)
        if not insertion_match:
            print("Error: Could not find </svg> tag.")
            sys.exit(1)
        
        insertion_point = insertion_match.start()
        
        # Build new path tags in order (0 to 5)
        new_paths_xml = ""
        for i in range(6):
            d = path_definitions[i]
            new_paths_xml += f'\n  <path id="Path{i}" d="{d}" style="fill:none;fill-opacity:0;stroke:#ff0000;stroke-linecap:round;stroke-linejoin:round;stroke-opacity:1" />'

        svg_content = svg_content[:insertion_point] + new_paths_xml + "\n" + svg_content[insertion_point:]

    # Clean up styles and notes
    svg_content = svg_content.replace('stroke-dasharray:298,1;stroke-dashoffset:0;', '')
    svg_content = svg_content.replace('Dashed cuts for perforation (48pt cut, 12pt stay)', f'Hard coded tabs (1pt gaps) at center of {args.mode}')

    with open(output_file, 'w') as f:
        f.write(svg_content)
    print(f"Successfully created {output_file}")

if __name__ == "__main__":
    main()
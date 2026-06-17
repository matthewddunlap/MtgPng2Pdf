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

def get_path_segments(x_min, y_min, x_max, y_max, r, mode='all', gap=1.0):
    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2
    half_gap = gap / 2.0
    top_y, bottom_y = y_min, y_max
    left_x, right_x = x_min, x_max
    k = 4.51
    all_segments = []
    
    def add_edge(x1, y1, x2, y2, is_broken):
        if is_broken:
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if x1 == x2:
                all_segments.append(f"M {x1:.2f},{y1:.2f} L {x1:.2f},{cy - half_gap:.2f}")
                all_segments.append(f"M {x1:.2f},{cy + half_gap:.2f} L {x1:.2f},{y2:.2f}")
            else:
                all_segments.append(f"M {x1:.2f},{y1:.2f} L {cx - half_gap:.2f},{y1:.2f}")
                all_segments.append(f"M {cx + half_gap:.2f},{y1:.2f} L {x2:.2f},{y1:.2f}")
        else:
            all_segments.append(f"M {x1:.2f},{y1:.2f} L {x2:.2f},{y2:.2f}")

    def add_corner(p0, p1, p2, p3, is_broken):
        if is_broken:
            s1, s2 = make_broken_bezier(p0, p1, p2, p3, r, gap)
            all_segments.extend([s1, s2])
        else:
            all_segments.append(f"M {p0[0]:.2f},{p0[1]:.2f} C {p1[0]:.2f},{p1[1]:.2f} {p2[0]:.2f},{p2[1]:.2f} {p3[0]:.2f},{p3[1]:.2f}")

    break_edges = mode in ['all', 'edges']
    break_radii = mode in ['all', 'radii']

    add_edge(center_x, top_y, x_max - r, top_y, break_edges)
    add_corner((x_max - r, y_min), (x_max - r + k, y_min), (x_max, y_min + r - k), (x_max, y_min + r), break_radii)
    add_edge(x_max, y_min + r, x_max, center_y, break_edges)
    add_edge(x_max, center_y, x_max, y_max - r, break_edges)
    add_corner((x_max, y_max - r), (x_max, y_max - r + k), (x_max - r + k, y_max), (x_max - r, y_max), break_radii)
    add_edge(x_max - r, y_max, center_x, y_max, break_edges)
    add_edge(center_x, y_max, x_min + r, y_max, break_edges)
    add_corner((x_min + r, y_max), (x_min + r - k, y_max), (x_min, y_max - r + k), (x_min, y_max - r), break_radii)
    add_edge(x_min, y_max - r, x_min, center_y, break_edges)
    add_edge(x_min, center_y, x_min, y_min + r, break_edges)
    add_corner((x_min, y_min + r), (x_min, y_min + r - k), (x_min + r - k, y_min), (x_min + r, y_min), break_radii)
    add_edge(x_min + r, y_min, center_x, y_min, break_edges)
    return " ".join(all_segments)

def main():
    parser = argparse.ArgumentParser(description='Generate broken SVG paths for card slots.')
    parser.add_argument('mode', choices=['all', 'edges', 'radii'], help='Where to place the 1pt breaks.')
    parser.add_argument('--template', default='inkscape_3x2_portrait_v1.0_uniform.svg', help='Uniform SVG template.')
    parser.add_argument('--output', help='Output SVG filename.')
    args = parser.parse_args()

    output_file = args.output
    if not output_file:
        suffix = f"_{args.mode}" if args.mode != 'edges' else ""
        output_file = args.template.replace('_uniform.svg', f'_tabs{suffix}.svg')

    try:
        with open(args.template, 'r') as f:
            svg_content = f.read()
    except FileNotFoundError:
        print(f"Error: Template {args.template} not found.")
        sys.exit(1)

    x_min, y_min = 43.44, 80.64
    x_max, y_max = 292.80, 259.20
    r, dx, dy = 8.20, 314.16 - 43.44, 275.04 - 80.64

    for row in range(3):
        for col in range(2):
            i = row * 2 + col
            d = get_path_segments(x_min + col*dx, y_min + row*dy, x_max + col*dx, y_max + row*dy, r, mode=args.mode)
            # Find the path with Path{i} and update its 'd' attribute
            pattern = rf'(<path\s+id="Path{i}"\s+d=")[^"]+(")'
            svg_content = re.sub(pattern, rf'\1{d}\2', svg_content)

    # Clean up styles and notes
    svg_content = svg_content.replace('stroke-dasharray:298,1;stroke-dashoffset:0;', '')
    svg_content = svg_content.replace('Dashed cuts for perforation (48pt cut, 12pt stay)', f'Hard coded tabs (1pt gaps) at center of {args.mode}')

    with open(output_file, 'w') as f:
        f.write(svg_content)
    print(f"Successfully created {output_file}")

if __name__ == "__main__":
    main()

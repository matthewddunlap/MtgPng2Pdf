"""
Registration mark generator for MtgPng2Pdf.
Generates baseline template JPG backgrounds with registration overlays.
"""

import os
from PIL import Image, ImageDraw

def create_letter_portrait_registration():
    # Letter size at 300 DPI: 8.5" x 11"
    width_px = 2550
    height_px = 3300

    # 1mm = 300 / 25.4 pixels
    mm_to_px = 300 / 25.4

    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)

    # Registration marks from inkscape_3x2_portrait_v1.svg (in mm)
    # Top Left: 5x5mm square, 10mm from top/left edges
    tl_x = 10.0 * mm_to_px
    tl_y = 10.0 * mm_to_px
    tl_w = 5.0 * mm_to_px
    tl_h = 5.0 * mm_to_px
    draw.rectangle([tl_x, tl_y, tl_x + tl_w, tl_y + tl_h], fill="black")

    t_px = 1.5 * mm_to_px
    arm_px = 20.0 * mm_to_px

    # Top Right: Outer corner at (205.9, 10.0)
    # L shape: Horizontal arm (left), Vertical arm (down)
    tr_x_outer = 205.9 * mm_to_px
    tr_y_outer = 10.0 * mm_to_px
    tr_poly = [
        (tr_x_outer - arm_px, tr_y_outer),        # Start of horizontal arm (left)
        (tr_x_outer, tr_y_outer),                 # Outer corner
        (tr_x_outer, tr_y_outer + arm_px),        # End of vertical arm (bottom)
        (tr_x_outer - t_px, tr_y_outer + arm_px), # Bottom-left of vertical arm
        (tr_x_outer - t_px, tr_y_outer + t_px),   # Inner corner
        (tr_x_outer - arm_px, tr_y_outer + t_px)  # Bottom-left of horizontal arm
    ]
    draw.polygon(tr_poly, fill="black")

    # Bottom Left: Outer corner at (10.0, 247.0)
    # L shape: Horizontal arm (right), Vertical arm (up)
    bl_x_outer = 10.0 * mm_to_px
    bl_y_outer = 247.0 * mm_to_px

    bl_poly = [
        (bl_x_outer + arm_px, bl_y_outer),        # Start of horizontal arm (right)
        (bl_x_outer, bl_y_outer),                 # Outer corner
        (bl_x_outer, bl_y_outer - arm_px),        # End of vertical arm (top)
        (bl_x_outer + t_px, bl_y_outer - arm_px), # Top-right of vertical arm
        (bl_x_outer + t_px, bl_y_outer - t_px),   # Inner corner
        (bl_x_outer + arm_px, bl_y_outer - t_px)  # Top-right of horizontal arm
    ]
    draw.polygon(bl_poly, fill="black")

    os.makedirs("assets", exist_ok=True)
    img.save("assets/letter_portrait_registration.jpg", quality=95)
    print("Created assets/letter_portrait_registration.jpg (6-card background, 20mm arms).")


def create_letter_portrait_8card_registration():
    # Letter size at 300 DPI: 8.5" x 11"
    width_px = 2550
    height_px = 3300

    # 1mm = 300 / 25.4 pixels
    mm_to_px = 300 / 25.4

    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)

    # Registration marks for 8-card layout at 5mm offset
    # Top Left: 5x5mm square, 5mm from top/left edges
    tl_x = 5.0 * mm_to_px
    tl_y = 5.0 * mm_to_px
    tl_w = 5.0 * mm_to_px
    tl_h = 5.0 * mm_to_px
    draw.rectangle([tl_x, tl_y, tl_x + tl_w, tl_y + tl_h], fill="black")

    t_px = 1.5 * mm_to_px
    arm_px = 15.0 * mm_to_px

    # Top Right: Outer corner at (210.9, 5.0)
    # L shape: Horizontal arm (left), Vertical arm (down)
    tr_x_outer = 210.9 * mm_to_px
    tr_y_outer = 5.0 * mm_to_px
    tr_poly = [
        (tr_x_outer - arm_px, tr_y_outer),        # Start of horizontal arm (left)
        (tr_x_outer, tr_y_outer),                 # Outer corner
        (tr_x_outer, tr_y_outer + arm_px),        # End of vertical arm (bottom)
        (tr_x_outer - t_px, tr_y_outer + arm_px), # Bottom-left of vertical arm
        (tr_x_outer - t_px, tr_y_outer + t_px),   # Inner corner
        (tr_x_outer - arm_px, tr_y_outer + t_px)  # Bottom-left of horizontal arm
    ]
    draw.polygon(tr_poly, fill="black")

    # Bottom Left: Outer corner at (5.0, 254.0)
    # L shape: Horizontal arm (right), Vertical arm (up)
    bl_x_outer = 5.0 * mm_to_px
    bl_y_outer = 254.0 * mm_to_px

    bl_poly = [
        (bl_x_outer + arm_px, bl_y_outer),        # Start of horizontal arm (right)
        (bl_x_outer, bl_y_outer),                 # Outer corner
        (bl_x_outer, bl_y_outer - arm_px),        # End of vertical arm (top)
        (bl_x_outer + t_px, bl_y_outer - arm_px), # Top-right of vertical arm
        (bl_x_outer + t_px, bl_y_outer - t_px),   # Inner corner
        (bl_x_outer + arm_px, bl_y_outer - t_px)  # Top-right of horizontal arm
    ]
    draw.polygon(bl_poly, fill="black")

    os.makedirs("assets", exist_ok=True)
    img.save("assets/letter_portrait_8card_registration.jpg", quality=95)
    print("Created assets/letter_portrait_8card_registration.jpg (8-card background, 15mm arms).")


if __name__ == "__main__":
    # Ensure both backgrounds are written to assets/
    create_letter_portrait_registration()
    create_letter_portrait_8card_registration()
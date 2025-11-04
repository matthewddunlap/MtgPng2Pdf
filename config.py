"""
Configuration constants for MtgPng2Pdf.
"""

from typing import Dict, Tuple, Set, Any
from reportlab.lib.pagesizes import letter, legal

# --- Configuration Constants for the image itself ---
TARGET_IMG_WIDTH_INCHES = 2.5
TARGET_IMG_HEIGHT_INCHES = 3.5

PAPER_SIZES_PT: Dict[str, Tuple[float, float]] = {
    "letter": letter, "legal": legal,
}
BASIC_LAND_NAMES: Set[str] = {
    "forest", "island", "mountain", "plains", "swamp"
}

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

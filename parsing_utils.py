"""
Parsing utilities for MtgPng2Pdf.
"""

import os
import re
import unicodedata
from typing import Optional, NamedTuple, Tuple

from config import PAPER_SIZES_PT

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
    # 1. Capture count, optional 'x', and trailing space(s)
    r"^\s*(?P<count>\d+)x?\s+"
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

"""
Card processing logic for MtgPng2Pdf.
"""

import os
import random
import re
import urllib.parse
from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Set, Union

from image_handler import ImageSource
from parsing_utils import parse_moxfield_line, normalize_card_name, parse_variant_filename
from config import BASIC_LAND_NAMES

# Regex to detect "Sideboard" heading (case-insensitive, optional leading spaces/hash)
SIDEBOARD_HEADING_RE = re.compile(r"^[\s#]*sideboard[\s#]*$", re.IGNORECASE)

def select_cards_with_priority_and_cycling(
    preferred_pool: List[ImageSource],
    general_pool: List[ImageSource],
    num_to_select: int,
    debug: bool = False,
    spell_sets_filter: Optional[List[str]] = None
) -> List[ImageSource]:
    """
    Selects cards by maximizing variety, prioritizing the preferred pool.
    It exhausts all unique cards (preferred then general) before cycling.
    """
    if not preferred_pool and not general_pool:
        return []

    selected: List[ImageSource] = []
    
    # Shuffle pools to ensure random selection within priority tiers
    shuffled_preferred = preferred_pool[:]
    if spell_sets_filter:
        def get_sort_key(source: ImageSource):
            _, src_set_code, src_collector_number = parse_variant_filename(source.original)
            for i, filter_set_str in enumerate(spell_sets_filter):
                if '-' in filter_set_str:
                    filter_set, filter_variant = filter_set_str.split('-', 1)
                    if src_set_code == filter_set and src_collector_number and src_collector_number.endswith(filter_variant):
                        return i
                elif src_set_code == filter_set_str:
                    return i
            return len(spell_sets_filter) # Should not happen if preferred_pool is built correctly
        shuffled_preferred.sort(key=get_sort_key)
    else:
        random.shuffle(shuffled_preferred)
    
    shuffled_general = general_pool[:]
    random.shuffle(shuffled_general)
    
    # The master list of unique sources, in order of priority
    master_selection_order = shuffled_preferred + shuffled_general
    
    if not master_selection_order:
        return []

    if debug:
        print(f"DEBUG: Master selection order for this card has {len(master_selection_order)} unique versions.")
        if shuffled_preferred:
            print(f"DEBUG:   - Preferred pool size: {len(shuffled_preferred)}")
        if shuffled_general:
            print(f"DEBUG:   - General pool size: {len(shuffled_general)}")

    pool_size = len(master_selection_order)
    for i in range(num_to_select):
        # Cycle through the master list to select the required number of cards
        selected.append(master_selection_order[i % pool_size])
        
    return selected

def process_deck_list(
    deck_list_path: str,
    all_cards_map: Dict[str, List[ImageSource]],
    skip_basic_land: bool,
    basic_land_sets_filter: Optional[List[str]],
    basic_land_set_mode: str,
    spell_sets_filter: Optional[List[str]],
    spell_set_mode: str,
    basic_land_sets_exclude: Optional[List[str]],
    spell_sets_exclude: Optional[List[str]],
    card_set_overrides: Dict[str, Dict[str, Union[List[str], str]]],
    debug: bool = False
) -> Tuple[List[ImageSource], List[str], Dict[str, Dict[str, Dict[str, int]]]]:
    """
    Processes a deck list, aggregating card counts before finding images.
    Returns the list of images, missing cards, and a manifest of selected cards.
    """
    images_to_print: List[ImageSource] = []
    missing_card_names: List[str] = []
    skipped_basic_lands_count: Dict[str, int] = defaultdict(int)
    selection_manifest: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    # Separate requests for main deck and sideboard
    deck_fully_specific_requests: Dict[Tuple[str, str, str], int] = defaultdict(int)
    deck_set_specific_requests: Dict[Tuple[str, str], int] = defaultdict(int)
    deck_generic_requests: Dict[str, int] = defaultdict(int)

    sideboard_fully_specific_requests: Dict[Tuple[str, str, str], int] = defaultdict(int)
    sideboard_set_specific_requests: Dict[Tuple[str, str], int] = defaultdict(int)
    sideboard_generic_requests: Dict[str, int] = defaultdict(int)

    original_card_names: Dict[str, str] = {}

    current_section = "Deck" # Can be "Deck" or "Sideboard"

    # --- Pass 1: Parse and Aggregate all lines from the deck list ---
    try:
        with open(deck_list_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                if not line:
                    if debug: print(f"DEBUG: Skipping empty line {line_num}.")
                    continue

                if SIDEBOARD_HEADING_RE.match(line):
                    current_section = "Sideboard"
                    if debug: print(f"DEBUG: Detected Sideboard heading at line {line_num}. Switching to Sideboard section.")
                    continue

                if not line[0].isdigit():
                    if debug: print(f"DEBUG: Skipping non-data line {line_num}: '{line}'")
                    continue

                entry = parse_moxfield_line(line)
                if not entry:
                    print(f"  Warning: Skipping malformed data line {line_num}: '{line}'")
                    missing_card_names.append(line)
                    continue

                normalized_name = normalize_card_name(entry.card_name)
                if normalized_name not in original_card_names:
                    original_card_names[normalized_name] = entry.card_name

                # Direct cards to the appropriate section's request dictionaries
                if current_section == "Deck":
                    if entry.set_code and entry.collector_number:
                        key = (normalized_name, entry.set_code, entry.collector_number)
                        deck_fully_specific_requests[key] += entry.count
                    elif entry.set_code:
                        key = (normalized_name, entry.set_code)
                        deck_set_specific_requests[key] += entry.count
                    else:
                        deck_generic_requests[normalized_name] += entry.count
                elif current_section == "Sideboard":
                    if entry.set_code and entry.collector_number:
                        key = (normalized_name, entry.set_code, entry.collector_number)
                        sideboard_fully_specific_requests[key] += entry.count
                    elif entry.set_code:
                        key = (normalized_name, entry.set_code)
                        sideboard_set_specific_requests[key] += entry.count
                    else:
                        sideboard_generic_requests[normalized_name] += entry.count

    except FileNotFoundError:
        print(f"Error: Deck list file not found: {deck_list_path}")
        return [], [], {}

    used_sources: Set[ImageSource] = set()

    # --- Helper to update manifest ---
    def update_manifest(section: str, original_name: str, sources: List[ImageSource]):
        for source in sources:
            filename = os.path.basename(urllib.parse.unquote(source.original))
            selection_manifest[section][original_name][filename] += 1

    # --- Process requests for both Deck and Sideboard ---
    sections_to_process = {
        "Deck": {
            "fully_specific": deck_fully_specific_requests,
            "set_specific": deck_set_specific_requests,
            "generic": deck_generic_requests
        },
        "Sideboard": {
            "fully_specific": sideboard_fully_specific_requests,
            "set_specific": sideboard_set_specific_requests,
            "generic": sideboard_generic_requests
        }
    }

    for section_name, requests_dict in sections_to_process.items():
        if debug: print(f"DEBUG: Processing {section_name} requests...")

        # --- Pass 2: Process FULLY-SPECIFIC requests first ---
        if debug and requests_dict["fully_specific"]: print(f"DEBUG: Processing {section_name} fully-specific card requests...")
        for (normalized_name, set_code, collector_number), count in requests_dict["fully_specific"].items():
            original_name = original_card_names.get(normalized_name, normalized_name)
            log_line = f"{count}x '{original_name} ({set_code.upper()}) {collector_number}'"

            is_basic_land = normalized_name in BASIC_LAND_NAMES
            if not is_basic_land and spell_set_mode == 'force' and spell_sets_filter and set_code not in spell_sets_filter:
                print(f"  NOT FOUND (Set Mismatch): {log_line}")
                missing_card_names.append(f"{count}x {original_name} ({set_code.upper()}) {collector_number}")
                continue
            
            found_source: Optional[ImageSource] = None
            for source in all_cards_map.get(normalized_name, []):
                _, f_set, f_num = parse_variant_filename(source.original)
                if f_set == set_code and f_num == collector_number:
                    found_source = source
                    break
            
            if found_source:
                if debug: print(f"DEBUG:   FOUND specific: {log_line}")
                selected_sources = [found_source] * count
                images_to_print.extend(selected_sources)
                update_manifest(section_name, original_name, selected_sources)
                for src in selected_sources: used_sources.add(src)
            else:
                print(f"  NOT FOUND (Fully-Specific): {log_line}")
                missing_card_names.append(f"{count}x {original_name} ({set_code.upper()}) {collector_number}")

        # --- Pass 3: Process SET-SPECIFIC requests ---
        if debug and requests_dict["set_specific"]: print(f"DEBUG: Processing {section_name} set-specific card requests...")
        for (normalized_name, set_code), count in requests_dict["set_specific"].items():
            original_name = original_card_names.get(normalized_name, normalized_name)
            log_line_base = f"{count}x '{original_name} ({set_code.upper()})'"

            is_basic_land = normalized_name in BASIC_LAND_NAMES
            if not is_basic_land and spell_set_mode == 'force' and spell_sets_filter and set_code not in spell_sets_filter:
                print(f"  NOT FOUND (Set Mismatch): {log_line_base}")
                missing_card_names.append(f"{count}x {original_name} ({set_code.upper()})")
                continue

            available_sources = all_cards_map.get(normalized_name, [])
            candidate_pool = [src for src in available_sources if src not in used_sources and parse_variant_filename(src.original)[1] == set_code]
            
            if not candidate_pool:
                print(f"  NOT FOUND (Set-Specific): No available images for {log_line_base}")
                missing_card_names.append(f"{count}x {original_name} ({set_code.upper()})")
                continue
                
            selected_sources = select_cards_with_priority_and_cycling([], candidate_pool, count, debug, [set_code])
            if debug: print(f"DEBUG:   Selected {len(selected_sources)} versions for {log_line_base}")
            
            images_to_print.extend(selected_sources)
            update_manifest(section_name, original_name, selected_sources)
            for src in selected_sources: used_sources.add(src)

        # --- Pass 4: Process GENERIC requests ---
        if debug and requests_dict["generic"]: print(f"DEBUG: Processing {section_name} generic card requests...")
        for normalized_name, count in requests_dict["generic"].items():
            original_name = original_card_names.get(normalized_name, normalized_name)

            is_basic_land = normalized_name in BASIC_LAND_NAMES
            if is_basic_land and skip_basic_land:
                if debug: print(f"DEBUG: Skipping basic land: {count}x '{original_name}'")
                skipped_basic_lands_count[original_name] += count
                continue
                
            # 1. Get all available sources for the card
            candidate_pool = all_cards_map.get(normalized_name, [])
            
            # 2. Apply the global EXCLUSION filter first
            current_sets_exclude = basic_land_sets_exclude if is_basic_land else spell_sets_exclude
            if current_sets_exclude:
                original_size = len(candidate_pool)
                candidate_pool = [
                    src for src in candidate_pool 
                    if parse_variant_filename(src.original)[1] not in current_sets_exclude
                ]
                if debug and len(candidate_pool) < original_size:
                    print(f"DEBUG: Excluded {original_size - len(candidate_pool)} versions of '{original_name}' due to set exclusion.")
            
            if not candidate_pool:
                print(f"  NOT FOUND (Generic): No available images for {count}x '{original_name}' after applying filters.")
                missing_card_names.append(f"{count}x {original_name}")
                continue
            
            # 3. Determine INCLUSION filters and mode
            current_sets_filter = basic_land_sets_filter if is_basic_land else spell_sets_filter
            current_set_mode = basic_land_set_mode if is_basic_land else spell_set_mode

            if not is_basic_land and normalized_name in card_set_overrides:
                override = card_set_overrides[normalized_name]
                current_sets_filter = override["sets"]
                current_set_mode = override["mode"]
                if debug:
                    print(f"DEBUG: Using override for '{original_name}': sets={current_sets_filter}, mode={current_set_mode}")

            preferred_pool: List[ImageSource] = []
            general_pool: List[ImageSource] = []

            if current_sets_filter:
                for src in candidate_pool:
                    _, src_set_code, src_collector_number = parse_variant_filename(src.original)
                    matched = False
                    for filter_set_str in current_sets_filter:
                        if '-' in filter_set_str:
                            filter_set, filter_variant = filter_set_str.split('-', 1)
                            if src_set_code == filter_set and src_collector_number and src_collector_number.endswith(filter_variant):
                                matched = True
                                break
                        elif src_set_code == filter_set_str:
                            matched = True
                            break
                    
                    if matched:
                        preferred_pool.append(src)
                    elif src not in used_sources:
                        general_pool.append(src)
                

                
                if current_set_mode == 'prefer':
                    if not preferred_pool:
                        # Fallback to general pool only if preferred pool is empty
                        selected_sources = select_cards_with_priority_and_cycling([], general_pool, count, debug, current_sets_filter)
                    else:
                        selected_sources = select_cards_with_priority_and_cycling(preferred_pool, [], count, debug, current_sets_filter)
                elif current_set_mode == 'minimum':
                    selected_sources = select_cards_with_priority_and_cycling(preferred_pool, general_pool, count, debug, current_sets_filter)
                elif current_set_mode == 'force':
                    if not preferred_pool:
                        print(f"  NOT FOUND (Spell): No '{original_name}' matching required sets: {current_sets_filter}")
                        missing_card_names.append(f"{count}x {original_name} (Set Mismatch: {current_sets_filter})")
                        continue
                    selected_sources = select_cards_with_priority_and_cycling(preferred_pool, [], count, debug, current_sets_filter)
            else:
                general_pool = [src for src in candidate_pool if src not in used_sources]
                selected_sources = select_cards_with_priority_and_cycling([], general_pool, count, debug)
            images_to_print.extend(selected_sources)
            update_manifest(section_name, original_name, selected_sources)
            for src in selected_sources: used_sources.add(src)

    if skipped_basic_lands_count:
        print("  Skipped the following basic lands:")
        for name, num in skipped_basic_lands_count.items():
            print(f"    - {num}x {name}")
            
    return images_to_print, list(set(missing_card_names)), selection_manifest

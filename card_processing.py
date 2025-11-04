"""
Card processing logic for MtgPng2Pdf.
"""

import os
import random
import urllib.parse
from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Set

from image_handler import ImageSource
from parsing_utils import parse_moxfield_line, normalize_card_name, parse_variant_filename
from config import BASIC_LAND_NAMES

def select_cards_with_priority_and_cycling(
    preferred_pool: List[ImageSource],
    general_pool: List[ImageSource],
    num_to_select: int,
    debug: bool = False
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
    debug: bool = False
) -> Tuple[List[ImageSource], List[str], Dict[str, Dict[str, int]]]:
    """
    Processes a deck list, aggregating card counts before finding images.
    Returns the list of images, missing cards, and a manifest of selected cards.
    """
    images_to_print: List[ImageSource] = []
    missing_card_names: List[str] = []
    skipped_basic_lands_count: Dict[str, int] = defaultdict(int)
    selection_manifest: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    fully_specific_requests: Dict[Tuple[str, str, str], int] = defaultdict(int)
    set_specific_requests: Dict[Tuple[str, str], int] = defaultdict(int)
    generic_requests: Dict[str, int] = defaultdict(int)
    original_card_names: Dict[str, str] = {}

    # --- Pass 1: Parse and Aggregate all lines from the deck list ---
    try:
        with open(deck_list_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                if not line or not line[0].isdigit():
                    if debug and line:
                        print(f"DEBUG: Skipping non-data line {line_num}: '{line}'")
                    continue

                entry = parse_moxfield_line(line)
                if not entry:
                    print(f"  Warning: Skipping malformed data line {line_num}: '{line}'")
                    missing_card_names.append(line)
                    continue

                normalized_name = normalize_card_name(entry.card_name)
                if normalized_name not in original_card_names:
                    original_card_names[normalized_name] = entry.card_name

                if entry.set_code and entry.collector_number:
                    key = (normalized_name, entry.set_code, entry.collector_number)
                    fully_specific_requests[key] += entry.count
                elif entry.set_code:
                    key = (normalized_name, entry.set_code)
                    set_specific_requests[key] += entry.count
                else:
                    generic_requests[normalized_name] += entry.count

    except FileNotFoundError:
        print(f"Error: Deck list file not found: {deck_list_path}")
        return [], [], {}

    used_sources: Set[ImageSource] = set()

    # --- Helper to update manifest ---
    def update_manifest(original_name: str, sources: List[ImageSource]):
        for source in sources:
            filename = os.path.basename(urllib.parse.unquote(source.original))
            selection_manifest[original_name][filename] += 1

    # --- Pass 2: Process FULLY-SPECIFIC requests first ---
    if debug and fully_specific_requests: print("DEBUG: Processing fully-specific card requests...")
    for (normalized_name, set_code, collector_number), count in fully_specific_requests.items():
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
            update_manifest(original_name, selected_sources)
            used_sources.add(found_source)
        else:
            print(f"  NOT FOUND (Fully-Specific): {log_line}")
            missing_card_names.append(f"{count}x {original_name} ({set_code.upper()}) {collector_number}")

    # --- Pass 3: Process SET-SPECIFIC requests ---
    if debug and set_specific_requests: print("DEBUG: Processing set-specific card requests...")
    for (normalized_name, set_code), count in set_specific_requests.items():
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
            
        selected_sources = select_cards_with_priority_and_cycling([], candidate_pool, count, debug)
        if debug: print(f"DEBUG:   Selected {len(selected_sources)} versions for {log_line_base}")
        
        images_to_print.extend(selected_sources)
        update_manifest(original_name, selected_sources)
        for src in selected_sources: used_sources.add(src)

    # --- Pass 4: Process GENERIC requests ---
    if debug and generic_requests: print("DEBUG: Processing generic card requests...")
    for normalized_name, count in generic_requests.items():
        original_name = original_card_names.get(normalized_name, normalized_name)

        is_basic_land = normalized_name in BASIC_LAND_NAMES
        if is_basic_land and skip_basic_land:
            if debug: print(f"DEBUG: Skipping basic land: {count}x '{original_name}'")
            skipped_basic_lands_count[original_name] += count
            continue
            
        # 1. Get all available sources that haven't been used yet
        candidate_pool = [src for src in all_cards_map.get(normalized_name, []) if src not in used_sources]
        
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

        preferred_pool: List[ImageSource] = []
        general_pool: List[ImageSource] = []

        if current_sets_filter:
            for src in candidate_pool:
                if parse_variant_filename(src.original)[1] in current_sets_filter:
                    preferred_pool.append(src)
                else:
                    general_pool.append(src)
            
            if current_set_mode == 'force':
                general_pool = []

            if current_set_mode == 'force' and not preferred_pool:
                print(f"  NOT FOUND (Spell): No '{original_name}' matching required sets: {current_sets_filter}")
                missing_card_names.append(f"{count}x {original_name} (Set Mismatch: {current_sets_filter})")
                continue
            
            if current_set_mode in ['prefer', 'minimum'] and not preferred_pool:
                available_sets = {parse_variant_filename(s.original)[1] for s in candidate_pool if parse_variant_filename(s.original)[1]}
                print(f"  WARN: No '{original_name}' found in preferred sets {current_sets_filter}. Available sets are: {sorted(list(available_sets))}. Falling back to all available sets.")
            
            selected_sources = select_cards_with_priority_and_cycling(preferred_pool, general_pool, count, debug)
        else:
            general_pool = candidate_pool
            selected_sources = select_cards_with_priority_and_cycling([], general_pool, count, debug)

        images_to_print.extend(selected_sources)
        update_manifest(original_name, selected_sources)
        for src in selected_sources: used_sources.add(src)

    if skipped_basic_lands_count:
        print("  Skipped the following basic lands:")
        for name, num in skipped_basic_lands_count.items():
            print(f"    - {num}x {name}")
            
    return images_to_print, list(set(missing_card_names)), selection_manifest

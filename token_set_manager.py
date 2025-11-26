"""
Token set management for MtgPng2Pdf.
"""

import json
import os
import requests
from datetime import datetime
from typing import Set, Optional

# Default token sets embedded as fallback (will be populated via --update-token-sets)
DEFAULT_TOKEN_SETS = {
    "tblc", "tneo", "tmid", "tvow", "tsnc", "tdmu", "tbro", "tone", "tmom", "tmat",
    "twoe", "twot", "tltr", "tcmm", "tclb", "tlci", "tmkm", "totc", "tblb", "tdsk",
    "tfdn", "ta25"
}

def load_token_sets(json_path: Optional[str] = None, debug: bool = False) -> Set[str]:
    """
    Load token sets from JSON file. Falls back to embedded default if file doesn't exist.
    
    Args:
        json_path: Path to token_sets.json. If None, uses default location.
        debug: Enable debug output.
    
    Returns:
        Set of token set codes (lowercase).
    """
    if json_path is None:
        json_path = os.path.join(os.path.dirname(__file__), "token_sets.json")
    
    if not os.path.exists(json_path):
        if debug:
            print(f"DEBUG: Token sets JSON not found at {json_path}, using embedded defaults")
        return DEFAULT_TOKEN_SETS.copy()
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            token_sets = set(data.get("token_sets", []))
            
            if debug:
                print(f"DEBUG: Loaded {len(token_sets)} token sets from {json_path}")
                if "last_updated" in data:
                    print(f"DEBUG: Token sets last updated: {data['last_updated']}")
            
            return token_sets
    
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load token sets from {json_path}: {e}")
        if debug:
            print("DEBUG: Falling back to embedded default token sets")
        return DEFAULT_TOKEN_SETS.copy()


def update_token_sets_from_api(json_path: Optional[str] = None, debug: bool = False) -> bool:
    """
    Fetch the latest token sets from Scryfall API and save to JSON file.
    
    Args:
        json_path: Path to save token_sets.json. If None, uses default location.
        debug: Enable debug output.
    
    Returns:
        True if successful, False otherwise.
    """
    if json_path is None:
        json_path = os.path.join(os.path.dirname(__file__), "token_sets.json")
    
    scryfall_api_url = "https://api.scryfall.com/sets"
    
    print(f"Fetching token sets from Scryfall API: {scryfall_api_url}")
    
    try:
        response = requests.get(scryfall_api_url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract token set codes
        token_sets = []
        for set_data in data.get("data", []):
            if set_data.get("set_type") == "token":
                set_code = set_data.get("code", "").lower()
                if set_code:
                    token_sets.append(set_code)
        
        if not token_sets:
            print("Error: No token sets found in API response")
            return False
        
        if debug:
            print(f"DEBUG: Found {len(token_sets)} token sets from Scryfall")
        
        # Create JSON structure
        output_data = {
            "token_sets": sorted(token_sets),
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "source": scryfall_api_url
        }
        
        # Write to file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"Successfully updated token sets: {json_path}")
        print(f"Total token sets: {len(token_sets)}")
        
        if debug:
            print(f"DEBUG: Sample token sets: {', '.join(sorted(token_sets)[:10])}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to fetch token sets from Scryfall API: {e}")
        return False
    except (IOError, json.JSONEncodeError) as e:
        print(f"Error: Failed to write token sets to {json_path}: {e}")
        return False


def is_token_set(set_code: str, token_sets: Set[str]) -> bool:
    """
    Check if a set code is a token set.
    
    Args:
        set_code: The set code to check (case-insensitive).
        token_sets: Set of known token set codes.
    
    Returns:
        True if the set code is a token set, False otherwise.
    """
    if not set_code:
        return False
    return set_code.lower() in token_sets

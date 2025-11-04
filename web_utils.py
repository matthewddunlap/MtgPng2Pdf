"""
Web utilities for MtgPng2Pdf.
"""

import os
import re
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin

import requests

# Global temp file tracking for cleanup
_temp_files: Set[str] = set()

def check_server_file_exists(url: str, debug: bool = False) -> bool:
    """Check if a file already exists at a given URL using a HEAD request."""
    if not url:
        return False
    if debug:
        print(f"DEBUG: Checking for file existence at: {url}")
    try:
        r = requests.head(url, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            if debug: print(f"DEBUG: File exists (200 OK) at {url}")
            return True
        if r.status_code == 404:
            if debug: print(f"DEBUG: File not found (404) at {url}")
            return False
        print(f"Warning: Received status {r.status_code} when checking {url}. Assuming it does not exist.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Warning: Network error while checking {url}: {e}. Assuming it does not exist.")
        return False

def upload_file_to_server(url: str, file_bytes: bytes, mime_type: str, debug: bool = False) -> bool:
    """Uploads file content (bytes) to a server URL using PUT."""
    if not url:
        print("Error: Cannot upload file, server URL is not configured.")
        return False
    if not file_bytes:
        print("Warning: No file content (bytes) to upload.")
        return False

    print(f"Uploading to: {url}")
    headers = {'Content-Type': mime_type}
    try:
        r = requests.put(url, data=file_bytes, headers=headers, timeout=60)
        r.raise_for_status()  # Raises an exception for 4xx/5xx status codes
        if 200 <= r.status_code < 300:
            print(f"Successfully uploaded. URL: {url}")
            return True
        else:
            # This part is less likely to be reached due to raise_for_status
            print(f"Error: Upload failed with status {r.status_code}.")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error: Upload failed due to a network error: {e}")
        return False

def list_webdav_directory(base_url: str, path: str = "/", debug: bool = False) -> List[Dict[str, str]]:
    """
    List files in a directory using WebDAV PROPFIND, with a fallback to simple HTTP listing.
    Returns a list of dicts with 'name' and 'href' (as a full URL) keys.
    """
    url = urljoin(base_url, path)
    if debug: print(f"DEBUG: Listing directory: {url}")
    
    # Build PROPFIND request body
    propfind_body = '''<?xml version="1.0" encoding="utf-8"?><D:propfind xmlns:D="DAV:"><D:prop><D:displayname/><D:resourcetype/></D:prop></D:propfind>'''
    
    req = urllib.request.Request(url, data=propfind_body.encode('utf-8'), headers={'Content-Type': 'application/xml; charset=utf-8', 'Depth': '1'}, method='PROPFIND')
    
    try:
        with urllib.request.urlopen(req) as response: content = response.read().decode('utf-8')
        
        # Parse XML response
        root = ET.fromstring(content); files = []; ns = {'d': 'DAV:'}
        
        for response_elem in root.findall('.//d:response', ns):
            href_elem = response_elem.find('d:href', ns)
            displayname_elem = response_elem.find('.//d:displayname', ns)
            resourcetype_elem = response_elem.find('.//d:resourcetype', ns)
            
            if href_elem is not None:
                relative_href = href_elem.text
                # Skip directories (they have a <collection/> element)
                if resourcetype_elem is not None and resourcetype_elem.find('d:collection', ns) is not None: continue
                
                # Get filename
                if displayname_elem is not None and displayname_elem.text: filename = displayname_elem.text
                else: filename = os.path.basename(urllib.parse.unquote(relative_href.rstrip('/')))
                
                if filename and filename.lower().endswith('.png'):
                    # Construct the full URL for the file
                    full_url = urljoin(base_url, relative_href)
                    files.append({'name': filename, 'href': full_url})
        
        if debug: print(f"DEBUG: Found {len(files)} PNG files in directory")
        return files
        
    except urllib.error.HTTPError as e:
        # If PROPFIND is not allowed, fall back to simple HTTP listing
        if e.code == 405: return list_http_directory(url, debug)
        else: print(f"Error listing directory: HTTP {e.code} - {e.reason}"); return []
    except Exception as e: print(f"Error listing directory: {e}"); return []

def list_http_directory(url: str, debug: bool = False) -> List[Dict[str, str]]:
    """
    Fallback method to list files from a simple HTTP directory listing.
    Parses HTML for links to PNG files. Returns full URLs.
    """
    if not url.endswith('/'): url += '/'
    if debug: print(f"DEBUG: Attempting HTTP directory listing: {url}")
    try:
        with urllib.request.urlopen(url) as response: content = response.read().decode('utf-8')
        
        # Simple regex to find links to PNG files
        png_pattern = r'href="([^"]+\.png)"'; matches = re.findall(png_pattern, content, re.IGNORECASE)
        
        files = []
        for match in matches:
            filename = os.path.basename(urllib.parse.unquote(match))
            full_url = urljoin(url, match)
            files.append({'name': filename, 'href': full_url})
        
        if debug: print(f"DEBUG: Found {len(files)} PNG files in HTTP directory listing")
        return files
    except Exception as e: print(f"Error listing HTTP directory: {e}"); return []

def download_image(url: str, dest_path: Optional[str] = None, debug: bool = False) -> Optional[str]:
    """
    Download an image from URL. If dest_path is None, saves to a temp file.
    Returns the path to the downloaded file, or None on error.
    """
    if debug: print(f"DEBUG: Downloading image from {url}")
    try:
        # Create temp file if no destination specified
        if dest_path is None:
            fd, dest_path = tempfile.mkstemp(suffix='.png'); os.close(fd)
            _temp_files.add(dest_path)
        
        # Download the file
        urllib.request.urlretrieve(url, dest_path)
        
        if debug: print(f"DEBUG: Downloaded to {dest_path}")
        return dest_path
    except Exception as e:
        print(f"Error downloading image from {url}: {e}")
        if dest_path and os.path.exists(dest_path):
            os.remove(dest_path); _temp_files.discard(dest_path)
        return None

def cleanup_temp_files():
    global _temp_files
    for temp_file in _temp_files:
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass
    _temp_files.clear()

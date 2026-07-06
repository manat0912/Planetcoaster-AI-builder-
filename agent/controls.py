"""Controls Scanner: scan game folders and parse config files to extract keybinds.

Provides auto-detection of game version (PC1/PC2) and custom key mappings
with safe keyboard/mouse defaults.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# Default control layouts for PC1 and PC2
PC1_DEFAULTS = {
    "camera_move_forward": "w",
    "camera_move_backward": "s",
    "camera_move_left": "a",
    "camera_move_right": "d",
    "camera_zoom_in": "pageup",
    "camera_zoom_out": "pagedown",
    "delete_object": "delete",
    "place_object": "left_click",
    "cancel_action": "escape",
    "rotate_object": "z",
    "height_adj": "shift",
    "menu_terrain": "t",
    "menu_paths": "p",
    "menu_scenery": "b",
    "menu_coasters": "r",
    "menu_rides": "y",
}

PC2_DEFAULTS = {
    "camera_move_forward": "w",
    "camera_move_backward": "s",
    "camera_move_left": "a",
    "camera_move_right": "d",
    "camera_zoom_in": "pageup",
    "camera_zoom_out": "pagedown",
    "delete_object": "delete",
    "place_object": "left_click",
    "cancel_action": "escape",
    "rotate_object": "z",
    "height_adj": "shift",
    "menu_terrain": "t",
    "menu_paths": "p",
    "menu_scenery": "b",
    "menu_coasters": "r",
    "menu_rides": "y",
}


def clean_key_name(raw_key: str) -> str:
    """Normalize raw key strings from Frontier config to PyAutoGUI key names."""
    k = raw_key.strip().lower()
    # Remove prefix like Key_ or Keyboard_
    k = re.sub(r'^(key_|keyboard_|button_)', '', k)
    
    # Map common Frontier key codes to pyautogui names
    mapping = {
        "page_up": "pageup",
        "page_down": "pagedown",
        "del": "delete",
        "esc": "escape",
        "lshift": "shift",
        "rshift": "shift",
        "lctrl": "ctrl",
        "rctrl": "ctrl",
        "lalt": "alt",
        "ralt": "alt",
        "mouse_1": "left_click",
        "mouse_2": "right_click",
        "mouse_3": "middle_click",
    }
    return mapping.get(k, k)


def parse_controls_xml(file_path: Path) -> dict[str, str]:
    """Parse control configuration XML (Frontier format) and extract bindings."""
    bindings = {}
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Frontier config style 1: tag name is the action, value is the key
        # e.g., <MoveForward>Key_W</MoveForward>
        # Frontier config style 2: <Binding Action="MoveForward" Key="Key_W" />
        
        # Check for style 1
        for elem in root.iter():
            name = elem.tag.lower()
            text = (elem.text or "").strip()
            
            # Fuzzy match standard actions
            if "forward" in name and text:
                bindings["camera_move_forward"] = clean_key_name(text)
            elif "backward" in name and text:
                bindings["camera_move_backward"] = clean_key_name(text)
            elif "left" in name and text:
                # distinguish between move left and turn/rotate
                if "move" in name or "pan" in name or name == "left":
                    bindings["camera_move_left"] = clean_key_name(text)
            elif "right" in name and text:
                if "move" in name or "pan" in name or name == "right":
                    bindings["camera_move_right"] = clean_key_name(text)
            elif "zoomin" in name and text:
                bindings["camera_zoom_in"] = clean_key_name(text)
            elif "zoomout" in name and text:
                bindings["camera_zoom_out"] = clean_key_name(text)
            elif "delete" in name and text:
                bindings["delete_object"] = clean_key_name(text)
                
        # Check for style 2 (Attribute style)
        for elem in root.findall(".//Binding"):
            action = elem.get("Action", "").lower()
            key = elem.get("Key", "")
            if not key:
                key = elem.get("Value", "")
            if not key:
                continue
                
            if "forward" in action:
                bindings["camera_move_forward"] = clean_key_name(key)
            elif "backward" in action:
                bindings["camera_move_backward"] = clean_key_name(key)
            elif "left" in action:
                bindings["camera_move_left"] = clean_key_name(key)
            elif "right" in action:
                bindings["camera_move_right"] = clean_key_name(key)
            elif "zoomin" in action:
                bindings["camera_zoom_in"] = clean_key_name(key)
            elif "zoomout" in action:
                bindings["camera_zoom_out"] = clean_key_name(key)
            elif "delete" in action:
                bindings["delete_object"] = clean_key_name(key)
    except Exception:
        # If parsing fails, just return whatever we managed to grab (or empty dict)
        pass
        
    return bindings


def scan_game_directory(path_str: str) -> dict[str, Any]:
    """Scan the given directory path recursively to detect game version and keybinds."""
    # Expand environment variables and user folder references
    expanded = os.path.expandvars(os.path.expanduser(path_str))
    root_path = Path(expanded)
    
    result = {
        "status": "Not Found",
        "game_version": "Planet Coaster 2 (Default)",
        "config_files_found": [],
        "controls": dict(PC2_DEFAULTS),
    }
    
    if not root_path.exists():
        result["status"] = f"Directory not found: {path_str}"
        return result
        
    result["status"] = "Scanned successfully"
    
    # 1. Detect game version
    # Check for executable files or path content
    executable_names = [f.name.lower() for f in root_path.glob("**/*") if f.is_file() and f.name.endswith(".exe")]
    
    is_pc1 = any("planetcoaster.exe" in name and "planetcoaster2.exe" not in name for name in executable_names)
    is_pc2 = any("planetcoaster2.exe" in name for name in executable_names)
    
    # If no executables are found, check the path names
    path_lower = str(root_path).lower()
    if not is_pc1 and not is_pc2:
        if "planet coaster 2" in path_lower or "planetcoaster2" in path_lower or "pc2" in path_lower:
            is_pc2 = True
        elif "planet coaster" in path_lower or "planetcoaster" in path_lower or "pc1" in path_lower:
            is_pc1 = True
            
    if is_pc1:
        result["game_version"] = "Planet Coaster 1"
        result["controls"] = dict(PC1_DEFAULTS)
    else:
        result["game_version"] = "Planet Coaster 2"
        result["controls"] = dict(PC2_DEFAULTS)
        
    # 2. Search for control configuration files
    # XML config files might be controls_remote.config.xml, ControlBindings.xml, etc.
    config_candidates = [
        "Controls_remote.config.xml",
        "Controls.config.xml",
        "ControlBindings.xml",
        "Game.config.xml",
    ]
    
    found_files = []
    # Search up to a depth of 3 to avoid slow deep searches on large drives
    for root, dirs, files in os.walk(root_path):
        # Limit depth
        depth = root[len(str(root_path)):].count(os.sep)
        if depth > 3:
            dirs.clear()  # don't go deeper
            continue
            
        for file in files:
            if file.lower().endswith(".xml") or any(c.lower() in file.lower() for c in config_candidates):
                found_files.append(Path(root) / file)
                
    result["config_files_found"] = [str(f.relative_to(root_path) if f.is_relative_to(root_path) else f) for f in found_files]
    
    # 3. Parse found XML files to override defaults
    parsed_bindings = {}
    for f in found_files:
        bindings = parse_controls_xml(f)
        parsed_bindings.update(bindings)
        
    if parsed_bindings:
        result["controls"].update(parsed_bindings)
        result["status"] += f" (Successfully parsed {len(parsed_bindings)} key bindings)"
    else:
        result["status"] += " (Using default key bindings)"
        
    return result

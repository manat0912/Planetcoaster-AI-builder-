"""Planet Coaster 2 — UI pixel coordinate map.

All coordinates are calibrated for 1920×1080.  Use ``scale_coords()`` to
convert to a different resolution.  All normalised variants (0.0-1.0) are
also provided for resolution-independent use.

Based on real game screenshots showing:
  - Top navigation bar: Entertainment / Coasters / Flat Rides / Tracked Rides /
                        Flumes / Pools / Facilities / Staff / Scenery
  - Terrain panel:  3 sub-tabs (Sculpt / Paint / Water), tool icon grid,
                    Intensity / Size / Hardness sliders.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple

# ── Base resolution ──────────────────────────────────────────────────────────
BASE_W, BASE_H = 1920, 1080


@dataclass
class UICoords:
    """All coordinates in BASE_W×BASE_H pixels (1920×1080)."""

    # ── Top navigation bar (icon tabs, approx y=25) ──────────────────────────
    # Observed in screenshot: Entertainment, Coasters, Flat Rides, Tracked Rides,
    # Flumes, Pools, Facilities, Staff, Scenery  (left-to-right)
    top_tabs: dict = field(default_factory=lambda: {
        "entertainment":  (63,  25),
        "coasters":       (130, 25),
        "flat_rides":     (200, 25),
        "tracked_rides":  (270, 25),
        "flumes":         (340, 25),
        "pools":          (410, 25),
        "facilities":     (475, 25),
        "staff":          (540, 25),
        "scenery":        (610, 25),
        # Terrain is reached via hotkey 't' or the mountain icon at far right
        "terrain":        (1750, 25),
    })

    # ── Terrain panel sub-tabs (top-left floating panel) ─────────────────────
    # Three icons at top of the Terrain panel:
    #   [mountain icon] = sculpt   [paintbrush] = paint   [droplet] = water
    terrain_panel_tabs: dict = field(default_factory=lambda: {
        "sculpt": (181, 80),   # mountain icon (1st tab)
        "paint":  (325, 80),   # paintbrush icon (2nd tab)
        "water":  (473, 80),   # droplet icon (3rd tab)
    })

    # ── Terrain sculpt tool icons (inside sculpt sub-tab) ────────────────────
    # Row 1: push_up, push_down, flatten, pinch, smooth_pinch
    # Row 2: smooth, rugged
    terrain_sculpt_tools: dict = field(default_factory=lambda: {
        "push_up":      (176, 197),
        "push_down":    (252, 197),
        "flatten":      (327, 197),
        "pinch":        (403, 197),
        "smooth_pinch": (479, 197),
        "smooth":       (289, 272),
        "rugged":       (365, 272),
    })

    # ── Terrain paint textures (inside paint sub-tab) ────────────────────────
    # After clicking the paint sub-tab, the texture palette appears.
    # These are approximate slot positions for the first visible textures.
    terrain_paint_textures: dict = field(default_factory=lambda: {
        "grass":        (85,  195),
        "dirt":         (160, 195),
        "sand":         (235, 195),
        "rock":         (310, 195),
        "cobblestone":  (385, 195),
        "snow":         (460, 195),
        "mud":          (85,  270),
        "jungle":       (160, 270),
        "asphalt":      (235, 270),
        "concrete":     (310, 270),
    })

    # ── Terrain sliders (approximate centres for click) ──────────────────────
    terrain_sliders: dict = field(default_factory=lambda: {
        "intensity_track": (450, 355),   # click track then drag
        "size_track":      (450, 407),
        "hardness_track":  (450, 460),
    })

    # ── Scenery / Building search bar ────────────────────────────────────────
    search: dict = field(default_factory=lambda: {
        "input_bar":        (120, 880),
        "clear_button":     (280, 880),
        "first_result":     (75,  935),
        "second_result":    (150, 935),
        "third_result":     (225, 935),
    })

    # ── Screen safe zone (game viewport, away from UI panels) ────────────────
    # The centre of the 3-D viewport (safe to click for terrain/placement)
    viewport_center: Tuple[int, int] = (960, 540)


# Singleton instance
PC2_UI = UICoords()


def scale_coords(xy: Tuple[int, int], screen_w: int, screen_h: int) -> Tuple[int, int]:
    """Scale a 1920×1080 coordinate to the actual screen resolution."""
    x = int(xy[0] * screen_w / BASE_W)
    y = int(xy[1] * screen_h / BASE_H)
    return x, y


def normalise(xy: Tuple[int, int]) -> Tuple[float, float]:
    """Convert absolute 1920×1080 pixel → normalised 0.0-1.0 coordinate."""
    return xy[0] / BASE_W, xy[1] / BASE_H


def from_normalised(nx: float, ny: float, screen_w: int = BASE_W, screen_h: int = BASE_H) -> Tuple[int, int]:
    """Convert normalised 0.0-1.0 coordinate → absolute pixel for a given resolution."""
    return int(nx * screen_w), int(ny * screen_h)


# ── Texture name → paint tab slot mapping ────────────────────────────────────
# Used by the autonomous agent to choose the right texture paint slot.
TEXTURE_ALIASES: dict[str, str] = {
    "asphalt texture":   "asphalt",
    "dirt texture":      "dirt",
    "sand texture":      "sand",
    "grass texture":     "grass",
    "rock texture":      "rock",
    "cobblestone":       "cobblestone",
    "cobblestone texture": "cobblestone",
    "jungle texture":    "jungle",
    "snow texture":      "snow",
    "concrete":          "concrete",
    "mud texture":       "mud",
}


def resolve_texture(name: str) -> str | None:
    """Return the canonical texture key for a given texture name (case-insensitive)."""
    key = name.lower().strip()
    if key in PC2_UI.terrain_paint_textures:
        return key
    return TEXTURE_ALIASES.get(key)


# ── Sculpt tool name → key mapping ───────────────────────────────────────────
SCULPT_TOOL_ALIASES: dict[str, str] = {
    "push up":          "push_up",
    "push/raise tool":  "push_up",
    "raise terrain":    "push_up",
    "push down":        "push_down",
    "pull/lower tool":  "push_down",
    "lower terrain":    "push_down",
    "flatten tool":     "flatten",
    "flatten":          "flatten",
    "smooth tool":      "smooth",
    "smooth terrain":   "smooth",
    "rugged":           "rugged",
    "pinch":            "pinch",
}


def resolve_sculpt_tool(name: str) -> str | None:
    """Return the canonical sculpt tool key for a given tool name (case-insensitive)."""
    key = name.lower().strip()
    if key in PC2_UI.terrain_sculpt_tools:
        return key
    return SCULPT_TOOL_ALIASES.get(key)

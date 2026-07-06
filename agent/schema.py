"""Structured schemas shared across the pipeline.

We keep the schemas as plain Python dicts / lightweight validators (no external
``jsonschema`` dependency) so the app stays easy to install through Pinokio.

Two data shapes flow through the system:

1. **Layout** - what the vision stage extracts from real-world blueprints.
   All coordinates are *normalized* to the 0..1 range so they are independent of
   the source image resolution; real-world size is captured separately in meters.

2. **Action plan** - the ordered list of in-game operations the controller runs.
   Coordinates here are already scaled to in-game units by the planner.
"""

from __future__ import annotations

from typing import Any

# ── Layout (vision output) ───────────────────────────────────────────────────
# {
#   "park_name": str,
#   "width_meters": float,
#   "height_meters": float,
#   "zones":     [{"name","theme","polygon":[[x,y],...]}],
#   "paths":     [{"width_meters","points":[[x,y],...]}],
#   "buildings": [{"name","theme","footprint":[[x,y],...],"height_meters"}],
#   "coasters":  [{"name","type","track":[{"x","y","z","banking"}]}],
#   "rides":     [{"name","type","x","y"}],
# }

LAYOUT_KEYS = ("park_name", "width_meters", "height_meters",
               "zones", "paths", "buildings", "coasters", "rides")

# ── Action plan (controller input) ───────────────────────────────────────────
# Each action is a dict with a "type" key. Supported types:
ACTION_TYPES = {
    "select_menu": {"menu"},
    "select_piece": {"name"},
    "place_piece": {"name", "x", "y", "z"},
    "place_track_node": {"x", "y", "z", "banking"},
    "sculpt_terrain": {"x", "y", "strength", "radius"},
    "place_path": {"x1", "y1", "x2", "y2", "width"},
    "click": {"x", "y"},
    "drag": {"x1", "y1", "x2", "y2"},
    "key": {"key"},
    "rotate_camera": {"dx", "dy"},
    "wait": {"seconds"},
    "screenshot": set(),
    "note": {"text"},
    "pan_camera": {"direction"},
    "zoom_camera": {"direction"},
    "delete_object": set(),
}


def empty_layout() -> dict[str, Any]:
    return {
        "park_name": "Untitled Park",
        "width_meters": 0.0,
        "height_meters": 0.0,
        "zones": [],
        "paths": [],
        "buildings": [],
        "coasters": [],
        "rides": [],
    }


def validate_layout(layout: Any) -> list[str]:
    """Return a list of human-readable problems (empty list == valid enough)."""
    problems: list[str] = []
    if not isinstance(layout, dict):
        return ["layout is not a JSON object"]
    for key in ("zones", "paths", "buildings", "coasters", "rides"):
        if key in layout and not isinstance(layout[key], list):
            problems.append(f"'{key}' should be a list")
    for dim in ("width_meters", "height_meters"):
        val = layout.get(dim)
        if val is not None and (not isinstance(val, (int, float)) or val < 0):
            problems.append(f"'{dim}' should be a non-negative number")
    return problems


def validate_plan(plan: Any) -> list[str]:
    """Validate an action plan; returns list of problems."""
    problems: list[str] = []
    if not isinstance(plan, list):
        return ["plan is not a JSON array"]
    for i, action in enumerate(plan):
        if not isinstance(action, dict):
            problems.append(f"action #{i} is not an object")
            continue
        atype = action.get("type")
        if atype not in ACTION_TYPES:
            problems.append(f"action #{i} has unknown type {atype!r}")
            continue
        missing = ACTION_TYPES[atype] - set(action.keys())
        if missing:
            problems.append(f"action #{i} ({atype}) missing fields: {sorted(missing)}")
    return problems

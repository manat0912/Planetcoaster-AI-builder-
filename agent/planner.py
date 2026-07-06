"""Planner: layout + in-game dimensions -> scaled, validated action plan.

The planner first computes a uniform *shrink-to-fit* scale so the whole park
lands inside the buildable area while preserving proportions and topology, then
either:

* asks the model to translate the layout into Planet Coaster build actions
  (``generate_plan``), or
* deterministically converts the layout to a coarse outline plan
  (``layout_to_outline_plan``) - handy for a fast offline "preview" that needs no
  API call.

All output coordinates are in in-game units, centered inside the buildable area.
"""

from __future__ import annotations

import json
from typing import Any

from .model import call_model
from .schema import validate_plan

SYSTEM = (
    "You are a Planet Coaster (1 & 2) build planner. You convert a normalized "
    "park layout into an ordered list of concrete in-game build actions using only "
    "the documented action vocabulary. You respect the provided uniform scale "
    "factor and buildable bounds so nothing is placed outside the park. You output "
    "JSON only. "
    "CRITICAL: You must use the built-in assets, generic building/scenery pieces, "
    "and ride/coaster types already built into the game (e.g. 'Castle Wall', 'Adventure Roof', "
    "'Drop Tower', 'Steel Coaster') instead of inventing custom names like 'Hogwarts Castle' or "
    "'Jurassic Park Discovery Center'. When selecting menus, use the exact menu names: "
    "'Terrain', 'Paths', 'Scenery', 'Coasters', 'Rides'."
)

PROMPT_TEMPLATE = """Convert the following normalized park LAYOUT into an ordered
Planet Coaster build plan.

LAYOUT (all coords normalized 0..1):
{layout}

BUILDABLE AREA:
- width_units: {width_units}
- height_units: {height_units}
- meters_per_unit: {meters_per_unit}
- uniform scale factor to apply to real meters -> units: {scale:.5f}
- park is centered with these unit offsets: origin_x={origin_x:.2f}, origin_y={origin_y:.2f}

Convert every normalized coordinate to in-game UNITS with:
    unit_x = origin_x + norm_x * {fit_w:.2f}
    unit_y = origin_y + norm_y * {fit_h:.2f}
    unit_z = norm_z * {fit_w:.2f}

{guidance_section}

Scaling & Fidelity Instructions:
- The real park dimensions are {real_w:.1f}m x {real_h:.1f}m.
- The in-game buildable area is {build_w_m:.1f}m x {build_h_m:.1f}m.
- The build is scaled down by a factor of {scale_ratio:.4f} relative to the real park.
- To make the scaled-down build look as close as possible to the real park, make sure to adjust/approximate where needed:
  1. Paths: Keep them usable (minimum width in-game is usually 4m / 1.0 unit). If path width scales down below 4m, clamp/set it to at least 4m.
  2. Spacing: Ensure buildings, rides, and coaster tracks have sufficient spacing so they do not clip or overlap.
  3. Coasters: Scale track node coordinates, but avoid making track elements or turns too tight or short, as game clearance limits require smooth shapes. Adjust the banking and heights to keep it looking realistic.

Built-In Asset & Menu Rules:
- The game only has standard built-in assets and themed pieces (Medieval/Fantasy, Adventure, Sci-Fi, Western, etc.). You MUST map custom/real-world landmark structures and rides to generic/standard piece names and ride/coaster types already in the game (e.g., use "Castle Tower" or "Castle Wall" instead of "Hogwarts Castle", "Adventure Temple" instead of "Jurassic Park Discovery Center", "B&M Wing Coaster" instead of "The Incredible Hulk Coaster", "Drop Tower" instead of "Doctor Doom's Fearfall").
- For the "select_menu" action, you MUST use one of the exact menu names: "Terrain", "Paths", "Scenery", "Coasters", or "Rides". (Do not use "Buildings", "Building", "Scenery/Buildings", etc.)

Terrain, Painting, and Water Rules:
- To shape terrain (e.g., carving trenches, flattening ground, raising hills), emit a `select_menu` for "Terrain", then a `select_piece` action with the name of the tool (e.g., "Flatten Tool", "Push/Raise Tool", "Pull/Lower Tool", "Smooth Tool"), followed by one or more `sculpt_terrain` actions.
- To apply materials or textures (e.g., painting sand, dirt, rock, grass), emit a `select_menu` for "Terrain", then a `select_piece` action with the name of the texture/material (e.g., "Sand Texture", "Dirt Texture", "Rock Texture"), followed by one or more `sculpt_terrain` actions.
- To place water features (e.g., lakes, rivers, ponds), emit a `select_menu` for "Terrain", then a `select_piece` action with the name of the water tool (e.g., "Water Tool" or "Calm Water"), followed by `place_piece` or `sculpt_terrain` actions.
- After every `select_piece`, emit a `wait` of at least 1.5 seconds to give the operator time to complete the menu search interaction before the next build action fires.

Camera Navigation Rules (IMPORTANT):
- The game camera does NOT move automatically. Before any cluster of build actions in a new area, you MUST emit camera actions to navigate there first.
- Use `zoom_camera` to set the overhead zoom level: emit it at the start of the plan and whenever moving to a distant area.
- Use `pan_camera` (with direction: "forward", "backward", "left", "right") to move the camera horizontally. Each `pan_camera` should have a "duration" field (seconds to hold the key, e.g. 0.5-2.0s). Follow every `pan_camera` with a `wait` of 0.3s.
- Before each zone's build actions, emit 2-4 `pan_camera` actions to position the camera over that zone, then a `zoom_camera` to set the right zoom level.
- Example camera navigation before a zone: zoom out first, pan to the zone location, zoom back in to a comfortable level.

Emit actions in this build order: camera setup, then terrain, then paths, then buildings, then
coaster track, then rides/theming. Use ONLY these action objects:

- {{"type":"select_menu","menu": string}}
- {{"type":"select_piece","name": string}}
- {{"type":"place_piece","name": string,"x": number,"y": number,"z": number}}
- {{"type":"place_track_node","x": number,"y": number,"z": number,"banking": number}}
- {{"type":"sculpt_terrain","x": number,"y": number,"strength": number,"radius": number}}
- {{"type":"place_path","x1": number,"y1": number,"x2": number,"y2": number,"width": number}}
- {{"type":"pan_camera","direction": string,"duration": number}}
- {{"type":"zoom_camera","direction": string,"clicks": number}}
- {{"type":"rotate_camera","dx": number,"dy": number}}
- {{"type":"wait","seconds": number}}
- {{"type":"note","text": string}}

CRITICAL OUTPUT FORMAT: Your entire response MUST be a single JSON array that starts
with '[' and ends with ']'. Do NOT wrap it in an object like {{"plan": [...]}}.
Do NOT include any text before or after the JSON array.
"""

# Common wrapper keys models use instead of returning a bare array
_WRAPPER_KEYS = ("plan", "actions", "build_plan", "steps", "build_actions", "result", "output")


def _unwrap_plan(raw: Any) -> Any:
    """If the model wrapped the array in an object, extract the array.

    Models (especially with JSON mode active) frequently return::

        {"plan": [{...}, ...]}   or   {"actions": [{...}, ...]}

    instead of a bare ``[{...}, ...]``.  This helper peeks inside and pulls
    out the first list value it finds under any known wrapper key.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        # Check known wrapper keys first
        for key in _WRAPPER_KEYS:
            if key in raw and isinstance(raw[key], list):
                return raw[key]
        # Fall back: return the first list value we find
        for val in raw.values():
            if isinstance(val, list):
                return val
    return raw  # Return as-is; validate_plan will report the problem



def compute_scale(layout: dict[str, Any], ingame: dict[str, Any]) -> dict[str, float]:
    """Compute uniform shrink-to-fit scale and centering offsets (in units)."""
    real_w = float(layout.get("width_meters") or 0) or 1.0
    real_h = float(layout.get("height_meters") or 0) or 1.0
    mpu = float(ingame["meters_per_unit"])

    build_w_m = ingame["width_units"] * mpu
    build_h_m = ingame["height_units"] * mpu

    scale = min(build_w_m / real_w, build_h_m / real_h)  # meters -> meters, uniform

    # park footprint in units after scaling
    fit_w = (real_w * scale) / mpu
    fit_h = (real_h * scale) / mpu

    origin_x = (ingame["width_units"] - fit_w) / 2.0
    origin_y = (ingame["height_units"] - fit_h) / 2.0

    return {
        "scale": scale / mpu,   # meters -> units factor (for reference)
        "fit_w": fit_w,
        "fit_h": fit_h,
        "origin_x": origin_x,
        "origin_y": origin_y,
    }


def generate_plan(
    layout: dict[str, Any], ingame: dict[str, Any], cfg: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Ask the model for a scaled, validated build plan."""
    s = compute_scale(layout, ingame)
    import json

    real_w = float(layout.get("width_meters") or 0) or 1.0
    real_h = float(layout.get("height_meters") or 0) or 1.0
    mpu = float(ingame["meters_per_unit"])
    build_w_m = ingame["width_units"] * mpu
    build_h_m = ingame["height_units"] * mpu
    scale_ratio = min(build_w_m / real_w, build_h_m / real_h)

    real_park_prompt = layout.get("real_park_prompt")
    if real_park_prompt:
        guidance_section = f"USER SCALE & DIMENSIONS GUIDANCE:\n{real_park_prompt}\n"
    else:
        guidance_section = ""

    prompt = PROMPT_TEMPLATE.format(
        layout=json.dumps(layout, indent=2),
        width_units=ingame["width_units"],
        height_units=ingame["height_units"],
        meters_per_unit=ingame["meters_per_unit"],
        scale=s["scale"],
        origin_x=s["origin_x"],
        origin_y=s["origin_y"],
        fit_w=s["fit_w"],
        fit_h=s["fit_h"],
        real_w=real_w,
        real_h=real_h,
        build_w_m=build_w_m,
        build_h_m=build_h_m,
        scale_ratio=scale_ratio,
        guidance_section=guidance_section,
    )
    plan = call_model(prompt, system=SYSTEM, expect_json=True, cfg=cfg)
    plan = _unwrap_plan(plan)
    problems = validate_plan(plan)
    if problems:
        # One-shot retry: explicitly ask for a bare JSON array
        retry_prompt = (
            "Your previous response was not a valid JSON array of build actions.\n"
            "Problems detected:\n- " + "\n- ".join(problems) + "\n\n"
            "OUTPUT REQUIREMENT: Respond with ONLY a JSON array that starts with '[' "
            "and ends with ']'. Each element must be an action object with a 'type' field. "
            "Do not wrap it in an object. Do not include any explanation.\n\n"
            "Original task:\n" + prompt
        )
        plan = call_model(retry_prompt, system=SYSTEM, expect_json=True, cfg=cfg)
        plan = _unwrap_plan(plan)
        problems = validate_plan(plan)
        if problems:
            raise ValueError("Planner produced an invalid plan:\n- " + "\n- ".join(problems))
    return plan


def _to_units(nx: float, ny: float, s: dict[str, float]) -> tuple[float, float]:
    return (
        round(s["origin_x"] + nx * s["fit_w"], 2),
        round(s["origin_y"] + ny * s["fit_h"], 2),
    )


def layout_to_outline_plan(
    layout: dict[str, Any], ingame: dict[str, Any]
) -> list[dict[str, Any]]:
    """Deterministic, API-free coarse plan: draws zone/building/coaster outlines.

    Useful as a fast "preview" that shows footprint and topology before committing
    to a full model-generated build.
    """
    s = compute_scale(layout, ingame)
    plan: list[dict[str, Any]] = [{"type": "note", "text": f"Preview outline for {layout.get('park_name')}"}]

    plan.append({"type": "select_menu", "menu": "Paths"})
    for path in layout.get("paths", []):
        pts = path.get("points", [])
        width = float(path.get("width_meters", 4)) / float(ingame["meters_per_unit"])
        for a, b in zip(pts, pts[1:]):
            x1, y1 = _to_units(a[0], a[1], s)
            x2, y2 = _to_units(b[0], b[1], s)
            plan.append({"type": "place_path", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                         "width": round(max(1.0, width), 2)})

    plan.append({"type": "select_menu", "menu": "Scenery"})
    for b in layout.get("buildings", []):
        fp = b.get("footprint", [])
        if not fp:
            continue
        cx = sum(p[0] for p in fp) / len(fp)
        cy = sum(p[1] for p in fp) / len(fp)
        ux, uy = _to_units(cx, cy, s)
        plan.append({"type": "note", "text": f"Building: {b.get('name')} ({b.get('theme')})"})
        plan.append({"type": "place_piece", "name": "Foundation Marker", "x": ux, "y": uy, "z": 0})

    plan.append({"type": "select_menu", "menu": "Coasters"})
    for c in layout.get("coasters", []):
        plan.append({"type": "note", "text": f"Coaster: {c.get('name')} ({c.get('type')})"})
        for node in c.get("track", []):
            ux, uy = _to_units(float(node.get("x", 0)), float(node.get("y", 0)), s)
            uz = round(float(node.get("z", 0)) * s["fit_w"], 2)
            plan.append({"type": "place_track_node", "x": ux, "y": uy, "z": uz,
                         "banking": float(node.get("banking", 0))})

    return plan

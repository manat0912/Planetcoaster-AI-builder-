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

from typing import Any

from .model import call_model
from .schema import validate_plan

SYSTEM = (
    "You are a Planet Coaster (1 & 2) build planner. You convert a normalized "
    "park layout into an ordered list of concrete in-game build actions using only "
    "the documented action vocabulary. You respect the provided uniform scale "
    "factor and buildable bounds so nothing is placed outside the park. You output "
    "JSON only."
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

Emit actions in this build order: terrain, then paths, then buildings, then
coaster track, then rides/theming. Use ONLY these action objects:

- {{"type":"select_menu","menu": string}}
- {{"type":"select_piece","name": string}}
- {{"type":"place_piece","name": string,"x": number,"y": number,"z": number}}
- {{"type":"place_track_node","x": number,"y": number,"z": number,"banking": number}}
- {{"type":"sculpt_terrain","x": number,"y": number,"strength": number,"radius": number}}
- {{"type":"place_path","x1": number,"y1": number,"x2": number,"y2": number,"width": number}}
- {{"type":"rotate_camera","dx": number,"dy": number}}
- {{"type":"wait","seconds": number}}
- {{"type":"note","text": string}}

Return ONLY a JSON array of action objects.
"""


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
    )
    plan = call_model(prompt, system=SYSTEM, expect_json=True, cfg=cfg)
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

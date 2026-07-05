"""Scan the in-game buildable area of Planet Coaster.

Two strategies:

* ``scan_ingame_dimensions_vision`` - screenshot the focused game window and ask
  the vision model to estimate the buildable area in grid units.
* ``manual_dimensions`` - deterministic values you calibrate once.

Both return the same dict shape:

    {"width_units": int, "height_units": int, "meters_per_unit": float}

``width_units`` * ``meters_per_unit`` gives the buildable width in meters, which
the planner uses to compute a uniform shrink-to-fit scale factor.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .model import call_model

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

SYSTEM = (
    "You analyze Planet Coaster screenshots and estimate the buildable park area "
    "in game grid units, using the visible terrain grid, park boundary fence and "
    "UI scale as references. You answer with JSON only."
)

PROMPT = """This is a screenshot of a Planet Coaster park in build mode.
Estimate the buildable area of the park in game GRID UNITS (one grid square = 1 unit).

Return ONLY this JSON:
{"width_units": integer, "height_units": integer, "meters_per_unit": number}

Use meters_per_unit = 4.0 unless the screenshot clearly indicates otherwise
(Planet Coaster's default build grid square is roughly 4 m across).
"""


def _grab_screenshot(path: Path) -> None:
    """Capture the primary monitor to *path*. Uses mss (cross-platform)."""
    import mss  # imported lazily so head-less use of the module never needs it

    path.parent.mkdir(parents=True, exist_ok=True)
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        img = sct.grab(monitor)
        import mss.tools

        mss.tools.to_png(img.rgb, img.size, output=str(path))


def scan_ingame_dimensions_vision(
    settle_seconds: float = 2.0, cfg: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Screenshot the game and let the model estimate the buildable area."""
    time.sleep(settle_seconds)
    shot = LOG_DIR / "park_scan.png"
    _grab_screenshot(shot)
    dims = call_model(PROMPT, images=[str(shot)], system=SYSTEM, expect_json=True, cfg=cfg)
    return _sanitize(dims)


def manual_dimensions(
    width_units: int = 200, height_units: int = 150, meters_per_unit: float = 4.0
) -> dict[str, Any]:
    """Deterministic calibration values (no game / vision needed)."""
    return _sanitize({
        "width_units": width_units,
        "height_units": height_units,
        "meters_per_unit": meters_per_unit,
    })


def _sanitize(dims: Any) -> dict[str, Any]:
    if not isinstance(dims, dict):
        dims = {}
    width = int(dims.get("width_units") or 200)
    height = int(dims.get("height_units") or 150)
    mpu = float(dims.get("meters_per_unit") or 4.0)
    return {
        "width_units": max(1, width),
        "height_units": max(1, height),
        "meters_per_unit": max(0.1, mpu),
    }

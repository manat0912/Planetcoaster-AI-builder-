"""Vision stage: real-world blueprints / maps / schematics -> structured layout.

Feeds the uploaded reference images to the configured vision model and asks for a
single normalized JSON layout. All spatial coordinates are normalized to 0..1
(fraction of the park's bounding box) so downstream scaling is resolution-free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from PIL import Image

from .model import call_model
from .schema import empty_layout, validate_layout

SYSTEM = (
    "You are an expert theme-park architectural extraction agent. You read "
    "blueprints, satellite maps, coaster POV frames, ride schematics and "
    "reference photos, and you return a single precise JSON description of the "
    "park's layout. You never invent measurements you cannot justify; when a real "
    "dimension is unknown you estimate it from typical theme-park scale and say so "
    "implicitly by keeping proportions consistent."
)

PROMPT = """Analyze ALL of the attached reference images together as one theme park.

Extract a single JSON object with EXACTLY these keys:

{
  "park_name": string,
  "width_meters": number,      // real-world extent of the whole park, west-east
  "height_meters": number,     // real-world extent, north-south
  "zones": [
    {"name": string, "theme": string, "polygon": [[x, y], ...]}
  ],
  "paths": [
    {"width_meters": number, "points": [[x, y], ...]}
  ],
  "buildings": [
    {"name": string, "theme": string, "footprint": [[x, y], ...], "height_meters": number}
  ],
  "coasters": [
    {"name": string, "type": string,
     "track": [{"x": number, "y": number, "z": number, "banking": number}]}
  ],
  "rides": [
    {"name": string, "type": string, "x": number, "y": number}
  ]
}

Rules:
- ALL x and y values (including z as height fraction) MUST be normalized to the
  range 0..1 relative to the park's bounding box. (0,0) = north-west corner,
  (1,1) = south-east corner. z is 0..1 as a fraction of width_meters.
- "banking" is degrees (-90..90).
- Map real themes to Planet Coaster-style theme names where obvious
  (e.g. Jurassic -> "Adventure", Harry Potter -> "Medieval/Fantasy").
- Keep the number of track nodes reasonable (<= 60 per coaster) but enough to
  capture the shape.
- Return ONLY the JSON object, no prose, no markdown fences.
"""


def _validate_image(path: str) -> None:
    path_obj = Path(path)
    if not path_obj.exists():
        raise ValueError(f"Image file not found: {path}")

    # Read first few bytes to check if it's a PDF
    try:
        with open(path, "rb") as f:
            header = f.read(4)
            if header == b"%PDF":
                raise ValueError(
                    f"File '{path_obj.name}' is a PDF document, not a supported image format. "
                    "Please convert your PDF pages to PNG or JPEG images before uploading."
                )
    except OSError:
        pass

    # Verify standard image formatting using PIL
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception:
        raise ValueError(
            f"File '{path_obj.name}' could not be identified as a valid image. "
            "Please ensure it is a valid PNG, JPEG, or WebP image."
        )


def extract_layout(
    image_paths: list[str],
    cfg: dict[str, Any] | None = None,
    real_park_prompt: str | None = None,
) -> dict[str, Any]:
    """Run the vision model over *image_paths* and return a validated layout dict."""
    if not image_paths:
        raise ValueError("No blueprint images provided.")

    for path in image_paths:
        _validate_image(path)

    prompt = PROMPT
    if real_park_prompt:
        prompt += f"\n\nUse the following user-provided scale, dimensions, or layout guidance for this park:\n{real_park_prompt}\n"

    layout = call_model(prompt, images=image_paths, system=SYSTEM, expect_json=True, cfg=cfg)

    problems = validate_layout(layout)
    if problems:
        raise ValueError("Vision model returned an invalid layout:\n- " + "\n- ".join(problems))

    # normalize missing keys so downstream code can rely on them
    base = empty_layout()
    base.update({k: v for k, v in layout.items() if v is not None})
    base["real_park_prompt"] = real_park_prompt
    return base

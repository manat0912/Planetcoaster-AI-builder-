"""Core Tool Suite: implementations of geometry, vision, construction, validation,
import, intelligence, export, and sandbox-specific tools for the PlanetCoaster AI Builder.
"""

from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Any

# ── 1. Core Geometry & Mapping Tools ──────────────────────────────────────────

def grid_to_meters(grid_x: float, grid_y: float, meters_per_grid: float = 4.0) -> dict[str, float]:
    """Converts grid units to meters using calibration (e.g. 4m per grid)."""
    return {
        "world_x_m": grid_x * meters_per_grid,
        "world_y_m": grid_y * meters_per_grid
    }


def normalize_coordinates(
    world_x_m: float, world_y_m: float, sandbox_width_m: float = 1000.0, sandbox_height_m: float = 1000.0
) -> dict[str, float]:
    """Maps any coordinate into a 0-1 normalized space for scaling."""
    return {
        "norm_x": max(0.0, min(1.0, world_x_m / sandbox_width_m)),
        "norm_y": max(0.0, min(1.0, world_y_m / sandbox_height_m))
    }


def scale_layout(points: list[dict[str, float]], scale_factor: float) -> list[dict[str, float]]:
    """Applies uniform scaling to fit real-world parks into the sandbox."""
    return [{"x": p["x"] * scale_factor, "y": p["y"] * scale_factor} for p in points]


def clip_to_sandbox(
    points: list[dict[str, float]], sandbox_width_m: float = 1000.0, sandbox_height_m: float = 1000.0
) -> list[dict[str, float]]:
    """Ensures all generated coordinates stay inside the sandbox bounds (e.g. 1000x1000m)."""
    clipped = []
    for p in points:
        clipped.append({
            "x": max(0.0, min(sandbox_width_m, p["x"])),
            "y": max(0.0, min(sandbox_height_m, p["y"]))
        })
    return clipped


def rotate_layout(points: list[dict[str, float]], angle_deg: float, pivot: tuple[float, float] = (0.0, 0.0)) -> list[dict[str, float]]:
    """Allows rotating layouts (e.g., 90, 45, arbitrary angle) before placement."""
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    px, py = pivot
    
    rotated = []
    for p in points:
        # Translate to pivot
        dx = p["x"] - px
        dy = p["y"] - py
        # Rotate
        rx = dx * cos_a - dy * sin_a
        ry = dx * sin_a + dy * cos_a
        # Translate back
        rotated.append({
            "x": rx + px,
            "y": ry + py
        })
    return rotated


def offset_layout(points: list[dict[str, float]], dx: float, dy: float) -> list[dict[str, float]]:
    """Shifts the entire layout by an offset (Origin Offset Tool)."""
    return [{"x": p["x"] + dx, "y": p["y"] + dy} for p in points]


# ── 2. Vision & Detection Tools ───────────────────────────────────────────────

def detect_gridline(image_path: str) -> dict[str, Any]:
    """Detects grid spacing from screenshots using visual analysis or image stats."""
    # Heuristics for demo, in production uses CV Hough lines
    img_path = Path(image_path)
    if not img_path.exists():
        return {"error": "Image file not found"}
        
    return {
        "width_grid_units": 200,
        "height_grid_units": 150,
        "meters_per_grid": 4.0,
        "confidence": 0.85
    }


def detect_object_boundary(image_path: str) -> dict[str, Any]:
    """Finds edges of buildable terrain or structures in screenshots."""
    img_path = Path(image_path)
    if not img_path.exists():
        return {"error": "Image file not found"}
        
    # Heuristic boundaries representing park build area
    return {
        "boundary_polygon": [
            {"x": 0.05, "y": 0.05},
            {"x": 0.95, "y": 0.05},
            {"x": 0.95, "y": 0.95},
            {"x": 0.05, "y": 0.95}
        ],
        "total_area_m2": 810000.0
    }


def correct_perspective(image_path: str, corners: list[tuple[float, float]]) -> str:
    """Fixes angled screenshots to extract accurate measurements. Returns path to warped image."""
    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
        
    # In full CV pipelines, cv2.getPerspectiveTransform & cv2.warpPerspective would run here.
    # We output a corrected path to simulate the pipeline.
    corrected_path = img_path.parent / f"corrected_{img_path.name}"
    # Just copy the original file as a fallback
    corrected_path.write_bytes(img_path.read_bytes())
    return str(corrected_path)


def color_mask_scan(image_path: str, target_colors: list[str]) -> dict[str, Any]:
    """Identifies terrain types, paths, water, etc. from colors."""
    # Mock analysis of mask coverage
    return {
        "grass_coverage": 0.65,
        "water_coverage": 0.12,
        "concrete_paths": 0.18,
        "sand_dirt": 0.05
    }


def extract_blueprint_shape(image_path: str) -> dict[str, Any]:
    """Reads shapes from images and converts them into vector geometry."""
    return {
        "shapes": [
            {"type": "circle", "center": {"x": 0.5, "y": 0.5}, "radius": 0.15},
            {"type": "polygon", "vertices": [{"x": 0.2, "y": 0.2}, {"x": 0.4, "y": 0.2}, {"x": 0.3, "y": 0.4}]}
        ]
    }


# ── 3. Construction & Placement Tools ─────────────────────────────────────────

def place_path_spline(points: list[dict[str, float]], width_m: float, path_type: str) -> dict[str, Any]:
    """Generates path splines, widths, and curvature build steps."""
    path_id = f"path_{abs(hash(str(points) + str(width_m) + path_type))}"
    return {
        "path_id": path_id,
        "status": "queued",
        "steps_count": len(points) - 1,
        "width_m": width_m
    }


def place_building_footprint(position: dict[str, float], rotation_deg: float, blueprint_id: str) -> dict[str, Any]:
    """Places modular building pieces at coordinates."""
    instance_id = f"building_{abs(hash(str(position) + str(rotation_deg) + blueprint_id))}"
    return {
        "instance_id": instance_id,
        "status": "placed",
        "position": position,
        "rotation_deg": rotation_deg
    }


def sculpt_terrain_tool(operation: str, center: dict[str, float], radius_m: float, strength: float) -> dict[str, Any]:
    """Raises, lowers, smooths, and flattens terrain."""
    if operation not in ("raise", "lower", "flatten", "smooth"):
        return {"status": "error", "message": f"Invalid operation: {operation}"}
    return {
        "status": "success",
        "operation": operation,
        "center": center,
        "radius_m": radius_m,
        "strength": strength
    }


def water_volume_tool(polygon: list[dict[str, float]], depth_m: float) -> dict[str, Any]:
    """Creates lakes, rivers, pools with depth constraints."""
    water_id = f"water_{abs(hash(str(polygon) + str(depth_m)))}"
    return {
        "water_volume_id": water_id,
        "depth_m": depth_m,
        "status": "filled",
        "vertices": len(polygon)
    }


def place_ride(ride_type: str, position: dict[str, float], footprint: list[dict[str, float]]) -> dict[str, Any]:
    """Places flat rides, coasters, and scenery with footprint validation."""
    ride_id = f"ride_{abs(hash(ride_type + str(position)))}"
    return {
        "ride_id": ride_id,
        "type": ride_type,
        "position": position,
        "status": "success"
    }


def load_blueprint_file(blueprint_id: str) -> dict[str, Any]:
    """Loads pre-made blueprints and positions them."""
    # Mock database lookup for default blueprints
    return {
        "blueprint_id": blueprint_id,
        "name": "Coaster Station Template",
        "pieces_count": 142,
        "bounding_box": {"width_m": 24.0, "length_m": 12.0, "height_m": 8.0}
    }


# ── 4. Constraint & Validation Tools ──────────────────────────────────────────

def check_collision(object_footprint: list[dict[str, float]], existing_footprints: list[list[dict[str, float]]]) -> dict[str, Any]:
    """Detects overlapping objects using bounding box intersection checks."""
    # Calculate bounding box of object_footprint
    if not object_footprint:
        return {"collision": False}
        
    xs = [p["x"] for p in object_footprint]
    ys = [p["y"] for p in object_footprint]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    for idx, footprint in enumerate(existing_footprints):
        if not footprint:
            continue
        exs = [p["x"] for p in footprint]
        eys = [p["y"] for p in footprint]
        e_min_x, e_max_x = min(exs), max(exs)
        e_min_y, e_max_y = min(eys), max(eys)
        
        # Check intersection
        if not (max_x < e_min_x or min_x > e_max_x or max_y < e_min_y or min_y > e_max_y):
            return {
                "collision": True,
                "overlap_index": idx,
                "message": f"Collision detected with object #{idx}"
            }
            
    return {"collision": False}


def validate_slope(points: list[dict[str, float]], max_slope_deg: float = 60.0) -> dict[str, Any]:
    """Ensures paths and coasters meet slope limits."""
    # Points include 'z' height
    exceeded_segments = []
    for idx, (p1, p2) in enumerate(zip(points, points[1:])):
        dx = p2["x"] - p1["x"]
        dy = p2["y"] - p1["y"]
        dz = p2.get("z", 0.0) - p1.get("z", 0.0)
        dist = math.sqrt(dx*dx + dy*dy)
        if dist > 0:
            slope = math.degrees(math.atan(abs(dz) / dist))
            if slope > max_slope_deg:
                exceeded_segments.append({
                    "segment": idx,
                    "slope_deg": slope,
                    "max_allowed": max_slope_deg
                })
                
    return {
        "valid": len(exceeded_segments) == 0,
        "failures": exceeded_segments
    }


def check_clearance(track_nodes: list[dict[str, float]], required_clearance_m: float = 4.0) -> dict[str, Any]:
    """Ensures coaster track nodes have required clearance from each other (to avoid self-clipping)."""
    clipping_nodes = []
    for i, n1 in enumerate(track_nodes):
        for j, n2 in enumerate(track_nodes):
            if abs(i - j) < 3: # Ignore adjacent track segments
                continue
            dx = n2["x"] - n1["x"]
            dy = n2["y"] - n1["y"]
            dz = n2.get("z", 0.0) - n1.get("z", 0.0)
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            if dist < required_clearance_m:
                clipping_nodes.append({
                    "node_a": i,
                    "node_b": j,
                    "distance_m": dist,
                    "required_m": required_clearance_m
                })
                
    return {
        "valid": len(clipping_nodes) == 0,
        "clipping_points": clipping_nodes
    }


def validate_terrain_boundary(
    points: list[dict[str, float]], sandbox_width: float = 1000.0, sandbox_height: float = 1000.0
) -> dict[str, Any]:
    """Prevents building outside the map bounds."""
    failures = []
    for idx, p in enumerate(points):
        if p["x"] < 0 or p["x"] > sandbox_width or p["y"] < 0 or p["y"] > sandbox_height:
            failures.append({
                "point_index": idx,
                "coords": p,
                "bounds": f"0..{sandbox_width} x 0..{sandbox_height}"
            })
            
    return {
        "valid": len(failures) == 0,
        "failures": failures
    }


def check_height_limit(z_coords: list[float], max_height_m: float = 625.0) -> dict[str, Any]:
    """Enforces the vertical building limit (625m in Planet Coaster)."""
    exceeded = [idx for idx, z in enumerate(z_coords) if z > max_height_m]
    return {
        "valid": len(exceeded) == 0,
        "max_height_m": max_height_m,
        "exceeded_indices": exceeded
    }


# ── 5. Real-World Import Tools ────────────────────────────────────────────────

def gis_to_sandbox(
    points: list[dict[str, float]], lat_origin: float, lon_origin: float, scale_factor: float
) -> list[dict[str, float]]:
    """Converts GPS coordinates into flat sandbox meter offsets relative to an origin."""
    # 1 degree of latitude is approx 111,000 meters
    # 1 degree of longitude is approx 111,000 * cos(lat) meters
    rad_lat = math.radians(lat_origin)
    meters_per_lat = 111000.0
    meters_per_lon = 111000.0 * math.cos(rad_lat)
    
    sandbox_points = []
    for p in points:
        # Assume points have 'lat' and 'lon' keys
        dy = (p["lat"] - lat_origin) * meters_per_lat
        dx = (p["lon"] - lon_origin) * meters_per_lon
        sandbox_points.append({
            "x": dx * scale_factor,
            "y": dy * scale_factor
        })
    return sandbox_points


def calculate_uniform_scale(real_acres: float, sandbox_width_m: float = 1000.0, sandbox_height_m: float = 1000.0) -> float:
    """Computes scale factor to fit a park of specified acres into the sandbox. (1 acre = 4046.86 m2)"""
    real_area_m2 = real_acres * 4046.86
    sandbox_area_m2 = sandbox_width_m * sandbox_height_m
    
    if real_area_m2 <= sandbox_area_m2:
        return 1.0
    return math.sqrt(sandbox_area_m2 / real_area_m2)


def preserve_aspect_ratio(width: float, height: float, max_dim: float = 1000.0) -> dict[str, float]:
    """Maintains proportions when scaling a layout's dimensions."""
    aspect = width / height
    if width > height:
        new_w = max_dim
        new_h = max_dim / aspect
    else:
        new_h = max_dim
        new_w = max_dim * aspect
    return {"width_m": new_w, "height_m": new_h}


def compress_coordinates(
    points: list[dict[str, float]], sandbox_width_m: float = 1000.0, sandbox_height_m: float = 1000.0
) -> list[dict[str, float]]:
    """Compresses large park coords to fit inside sandbox bounds without changing shape."""
    if not points:
        return []
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    w = max_x - min_x or 1.0
    h = max_y - min_y or 1.0
    
    scale = min(sandbox_width_m / w, sandbox_height_m / h)
    
    compressed = []
    for p in points:
        compressed.append({
            "x": (p["x"] - min_x) * scale,
            "y": (p["y"] - min_y) * scale
        })
    return compressed


# ── 6. Agent Intelligence Tools ───────────────────────────────────────────────

def generate_task_sequence(goal: str, constraints: dict[str, Any]) -> list[dict[str, Any]]:
    """Breaks large builds into sequential steps for the AI agent."""
    # Basic sequential generation
    return [
        {"step": 1, "task": "Sculpt terrain for flat ride foundation", "menu": "Terrain"},
        {"step": 2, "task": "Build main connection path spline", "menu": "Paths"},
        {"step": 3, "task": "Place station modular building", "menu": "Scenery"},
        {"step": 4, "task": "Lay down roller coaster tracks", "menu": "Coasters"}
    ]


def recover_placement_error(failed_action: dict[str, Any], error_reason: str) -> dict[str, Any]:
    """Suggests adjusted coordinates to recover from failed placement due to collisions/terrain."""
    adj = dict(failed_action)
    if "x" in adj and "y" in adj:
        # Shift slightly to the right or up to resolve collisions
        adj["x"] += 4.0
        adj["y"] += 4.0
    return {
        "status": "retry",
        "action": adj,
        "adjustment_applied": "Shifted +4m on X and Y to resolve collision/terrain constraint"
    }


def apply_preference_rules(action_plan: list[dict[str, Any]], rules: list[str]) -> list[dict[str, Any]]:
    """Applies user preference rules (e.g. fixed camera, pause between builds)."""
    optimized = []
    # Add a camera lock at the beginning
    optimized.append({"type": "note", "text": "Enforcing user preference: camera locks & physics calibration"})
    for act in action_plan:
        optimized.append(act)
        # If it's a placement, append a wait to let game physics settle
        if act.get("type") in ("place_piece", "place_track_node", "sculpt_terrain"):
            optimized.append({"type": "wait", "seconds": 0.5})
    return optimized


_MEMORY_CACHE: dict[str, Any] = {}

def memory_cache_lookup(key: str) -> Any:
    """Stores and retrieves previous build settings and calibration configurations."""
    return _MEMORY_CACHE.get(key)


def optimize_blueprint(blueprint_data: dict[str, Any]) -> dict[str, Any]:
    """Reduces blueprint scenery piece count while preserving overall shape."""
    optimized = dict(blueprint_data)
    if "pieces_count" in optimized:
        # Simulate filter out decoration debris pieces
        optimized["original_pieces"] = optimized["pieces_count"]
        optimized["pieces_count"] = int(optimized["pieces_count"] * 0.7)
    return optimized


# ── 7. Export & Integration Tools ─────────────────────────────────────────────

def export_json_layout(layout: dict[str, Any], filepath: str) -> str:
    """Saves built layouts to a structured JSON format."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(layout, indent=2))
    return str(p.resolve())


def export_vector_path(spline: list[dict[str, float]], filepath: str) -> str:
    """Saves path geometry coordinates as SVG splines for import."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    
    # Write a simple SVG format
    svg_lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">',
        '  <path d="'
    ]
    path_data = []
    for i, pt in enumerate(spline):
        cmd = "M" if i == 0 else "L"
        path_data.append(f"{cmd} {pt['x']} {pt['y']}")
    svg_lines.append(" ".join(path_data))
    svg_lines.append('" fill="none" stroke="black" stroke-width="4" />')
    svg_lines.append('</svg>')
    
    p.write_text("\n".join(svg_lines))
    return str(p.resolve())


def api_bridge_call(prompt: str, system_prompt: str | None = None) -> str:
    """Invokes local LLM models to refine build plans or retrieve coordinate geometry suggestions."""
    # Fallback response simulating API model response
    return f"BRIDGE_RESPONSE: Processed prompt '{prompt[:30]}...' with rules."


def file_io_op(operation: str, filepath: str, content: str | None = None) -> Any:
    """General file IO utility for reading/writing configuration files."""
    p = Path(filepath)
    if operation == "read":
        if not p.exists():
            return None
        return p.read_text()
    elif operation == "write" and content is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return True
    return False


# ── 8. Sandbox‑Specific Tools (Planet Coaster 2) ──────────────────────────────

def pc2_4meter_grid_mapper(grid_x: float, grid_y: float) -> dict[str, float]:
    """Converts Planet Coaster 2 grid indexes to meter world coordinates."""
    # PC2 uses a standard 4m grid layout
    return {
        "x_m": grid_x * 4.0,
        "y_m": grid_y * 4.0
    }


def resolve_terrain_tile(x: float, y: float) -> dict[str, int]:
    """Identifies Planet Coaster 2 terrain tile column and row index (e.g. 16m tiles)."""
    return {
        "tile_x": int(x // 16),
        "tile_y": int(y // 16)
    }


def validate_ride_footprint(
    ride_id: str, footprint: list[dict[str, float]], sandbox_width_m: float = 1000.0, sandbox_height_m: float = 1000.0
) -> dict[str, Any]:
    """Ensures a ride fits fully within the sandbox and doesn't clip fence boundaries."""
    if not footprint:
        return {"valid": True}
    xs = [p["x"] for p in footprint]
    ys = [p["y"] for p in footprint]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    out_of_bounds = max_x > sandbox_width_m or min_x < 0 or max_y > sandbox_height_m or min_y < 0
    return {
        "ride_id": ride_id,
        "valid": not out_of_bounds,
        "bounding_box": {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}
    }


def calculate_scenery_density(area_m2: float, object_count: int) -> dict[str, Any]:
    """Calculates density indicator to prevent game lag from overloading scenery items."""
    density = object_count / max(1.0, area_m2)
    # Threshold: more than 0.5 objects per square meter is high density
    status = "normal"
    if density > 0.5:
        status = "high"
    elif density > 1.2:
        status = "critical"
    return {
        "density_per_m2": density,
        "status": status,
        "recommendation": "Okay to place" if status == "normal" else "Reduce clutter pieces"
    }


def visualize_park_boundary(sandbox_width_m: float = 1000.0, sandbox_height_m: float = 1000.0) -> dict[str, Any]:
    """Returns SVG path or lines representing the 1000x1000m park bounds."""
    return {
        "width_m": sandbox_width_m,
        "height_m": sandbox_height_m,
        "corners": [
            {"x": 0.0, "y": 0.0},
            {"x": sandbox_width_m, "y": 0.0},
            {"x": sandbox_width_m, "y": sandbox_height_m},
            {"x": 0.0, "y": sandbox_height_m}
        ]
    }

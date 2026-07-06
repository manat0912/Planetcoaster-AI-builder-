"""Autonomous Planet Coaster AI Agent.

This module implements the closed-loop:

    screenshot → Gemini vision → structured JSON decision → PyDirectInput actions

Gemini sees:
  1. A reference screenshot of what to build (optional — can be a real park photo)
  2. The current game screen
  3. A compact park spatial-memory map showing what has already been built

Gemini outputs a JSON decision that tells this module:
  - Which phase it is in (terrain sculpt, paint, search asset, place object, navigate)
  - Where on screen to act (normalised 0..1 coordinates)
  - Which UI tab / sub-tool to activate
  - Whether the current area is finished

This module then converts that decision into PyDirectInput hardware-level
mouse and keyboard actions so Planet Coaster actually registers them.

Safety
------
* A background daemon thread monitors for Esc/Q to halt the agent instantly.
* PyDirectInput FAILSAFE is enabled.
* Dry-run mode logs decisions without moving the mouse.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

# ── input backend (pydirectinput preferred, pyautogui fallback) ───────────────
try:
    import pydirectinput as _pdi
    _pdi.FAILSAFE = True
    _INPUT = "pydirectinput"
except ImportError:
    import pyautogui as _pdi  # type: ignore[no-redef]
    _pdi.FAILSAFE = True
    _INPUT = "pyautogui"

import mss

from .model import load_config
from .ui_map import PC2_UI, scale_coords, from_normalised, resolve_texture, resolve_sculpt_tool
from .spatial_memory import ParkSpatialMemory

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Global abort flag ─────────────────────────────────────────────────────────
ABORT = False


def _start_kill_switch() -> None:
    """Background thread: press ESC or Q to stop the agent."""
    global ABORT
    try:
        import keyboard  # pip install keyboard
        print("[SAFETY] Kill-switch active. Press ESC or Q to stop the agent.")
        while not ABORT:
            if keyboard.is_pressed("esc") or keyboard.is_pressed("q"):
                print("\n[!] EMERGENCY STOP detected. Halting agent.")
                ABORT = True
                # Release any keys that might be stuck
                for k in ("shift", "w", "a", "s", "d"):
                    try:
                        _pdi.keyUp(k)
                    except Exception:
                        pass
                try:
                    _pdi.mouseUp()
                    _pdi.mouseUp(button="middle")
                except Exception:
                    pass
            time.sleep(0.05)
    except ImportError:
        print("[SAFETY] 'keyboard' package not installed. ESC kill-switch unavailable.")


# ── Screen capture ────────────────────────────────────────────────────────────

def capture_screen(out_path: str = str(LOG_DIR / "current_state.png")) -> str:
    """Capture the primary monitor and return the file path."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        sct.shot(output=out_path)
    return out_path


def _screen_size() -> tuple[int, int]:
    with mss.mss() as sct:
        m = sct.monitors[1]
        return m["width"], m["height"]


# ── Coordinate helpers ────────────────────────────────────────────────────────

def _px(norm_x: float, norm_y: float) -> tuple[int, int]:
    """Convert Gemini normalised coords to absolute screen pixels."""
    sw, sh = _screen_size()
    return int(norm_x * sw), int(norm_y * sh)


def _ui_px(abs_1080: tuple[int, int]) -> tuple[int, int]:
    """Scale a 1920×1080 UI coordinate to the current screen."""
    sw, sh = _screen_size()
    return scale_coords(abs_1080, sw, sh)


# ── Mathematical drag paths ───────────────────────────────────────────────────

def human_drag(
    sx: int, sy: int,
    ex: int, ey: int,
    steps: int = 30,
    pattern: str = "linear",
    button: str = "left",
) -> None:
    """Smooth hardware-level drag (held mouse button + move)."""
    _pdi.moveTo(sx, sy)
    _pdi.mouseDown(button=button)
    time.sleep(0.08)

    if pattern == "spiral":
        cx, cy = sx, sy
        max_r = math.hypot(ex - sx, ey - sy)
        for i in range(steps):
            angle = 0.35 * i
            r = (i / steps) * max_r
            _pdi.moveTo(int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle)))
            time.sleep(0.018)

    elif pattern == "sinusoidal":
        for i in range(steps):
            t = i / steps
            cx = int(sx + (ex - sx) * t)
            cy = int(sy + (ey - sy) * t + math.sin(t * math.pi * 4) * 35)
            _pdi.moveTo(cx, cy)
            time.sleep(0.018)

    else:  # linear
        for i in range(steps):
            t = i / steps
            _pdi.moveTo(int(sx + (ex - sx) * t), int(sy + (ey - sy) * t))
            time.sleep(0.015)

    _pdi.mouseUp(button=button)
    time.sleep(0.15)


# ── UI interaction helpers ────────────────────────────────────────────────────

def click_ui(coord_1080: tuple[int, int], wait: float = 0.3) -> None:
    """Click a known UI element (given in 1920×1080 coords)."""
    x, y = _ui_px(coord_1080)
    _pdi.moveTo(x, y, duration=0.15)
    _pdi.click()
    time.sleep(wait)


def type_text(text: str) -> None:
    """Type a string using pydirectinput/pyautogui typewrite."""
    try:
        _pdi.typewrite(text, interval=0.05)
    except AttributeError:
        # pydirectinput may not have typewrite; fall back char by char
        for ch in text:
            _pdi.press(ch)
            time.sleep(0.05)


def press_key(key: str, wait: float = 0.1) -> None:
    _pdi.press(key)
    time.sleep(wait)


# ── Terrain tool activation ───────────────────────────────────────────────────

def activate_terrain_sculpt_tool(tool_name: str, log: Callable) -> None:
    """Press T to open terrain, click sculpt tab, then click the correct tool icon."""
    key = resolve_sculpt_tool(tool_name)
    if key is None:
        log(f"[ui] Unknown sculpt tool '{tool_name}' — skipping tool selection.")
        return
    press_key("t", wait=0.8)                                         # open terrain panel
    click_ui(PC2_UI.terrain_panel_tabs["sculpt"], wait=0.4)          # sculpt tab
    coord = PC2_UI.terrain_sculpt_tools.get(key)
    if coord:
        click_ui(coord, wait=0.3)
    log(f"[ui] Activated sculpt tool: {key}")


def activate_terrain_paint_texture(texture_name: str, log: Callable) -> None:
    """Press T, click paint tab, then click the correct texture slot."""
    key = resolve_texture(texture_name)
    if key is None:
        log(f"[ui] Unknown texture '{texture_name}' — skipping.")
        return
    press_key("t", wait=0.8)                                         # open terrain panel
    click_ui(PC2_UI.terrain_panel_tabs["paint"], wait=0.4)           # paint tab
    coord = PC2_UI.terrain_paint_textures.get(key)
    if coord:
        click_ui(coord, wait=0.3)
    log(f"[ui] Activated paint texture: {key}")


def activate_water_tool(log: Callable) -> None:
    """Press T, click water tab."""
    press_key("t", wait=0.8)
    click_ui(PC2_UI.terrain_panel_tabs["water"], wait=0.4)
    log("[ui] Activated water tool.")


# ── Asset search ──────────────────────────────────────────────────────────────

def execute_search(keyword: str, log: Callable) -> None:
    """Clear search, type keyword, press Enter, wait for results, click first slot."""
    log(f"[search] Searching for '{keyword}'…")
    click_ui(PC2_UI.search["clear_button"], wait=0.2)
    click_ui(PC2_UI.search["input_bar"], wait=0.3)
    # Select all and clear
    _pdi.hotkey("ctrl", "a") if hasattr(_pdi, "hotkey") else (press_key("ctrl"), press_key("a"))
    press_key("delete", wait=0.1)
    type_text(keyword)
    press_key("return", wait=1.0)   # wait for results to load
    click_ui(PC2_UI.search["first_result"], wait=0.5)
    log(f"[search] Selected first result for '{keyword}'.")


# ── Camera navigation ─────────────────────────────────────────────────────────

def pan_camera(direction: str, duration: float = 0.8, log: Callable = print) -> None:
    """Hold a WASD key to pan the camera."""
    key_map = {"forward": "w", "backward": "s", "left": "a", "right": "d"}
    key = key_map.get(direction.lower(), "w")
    log(f"[camera] pan {direction} ({duration:.1f}s)")
    _pdi.keyDown(key)
    time.sleep(duration)
    _pdi.keyUp(key)
    time.sleep(0.2)


def zoom_camera(direction: str, clicks: int = 5, log: Callable = print) -> None:
    """Page-up/down to zoom."""
    key = "pageup" if direction.lower() == "in" else "pagedown"
    log(f"[camera] zoom {direction} ({clicks} clicks)")
    for _ in range(clicks):
        press_key(key, wait=0.07)


def navigate_to_sector(
    r: int, c: int,
    rows: int, cols: int,
    current_r: int, current_c: int,
    log: Callable,
) -> None:
    """Naive camera pan from current grid sector to target sector using WASD."""
    dr = r - current_r
    dc = c - current_c
    pan_dur = 0.6  # seconds per grid step
    if dc > 0:
        pan_camera("right", duration=abs(dc) * pan_dur, log=log)
    elif dc < 0:
        pan_camera("left", duration=abs(dc) * pan_dur, log=log)
    if dr > 0:
        pan_camera("backward", duration=abs(dr) * pan_dur, log=log)
    elif dr < 0:
        pan_camera("forward", duration=abs(dr) * pan_dur, log=log)


def cinematic_audit(log: Callable) -> list[str]:
    """Sweep the camera to capture high/profile angle screenshots for Gemini audit."""
    log("[audit] Running 3-D cinematic audit sweep…")
    paths = []

    # Zoom up
    for _ in range(6):
        press_key("pageup", wait=0.07)
    time.sleep(0.2)
    p1 = str(LOG_DIR / "audit_high.png")
    capture_screen(p1)
    paths.append(p1)

    # Orbit via middle-mouse drag
    sw, sh = _screen_size()
    cx, cy = sw // 2, sh // 2
    _pdi.moveTo(cx, cy)
    _pdi.mouseDown(button="middle")
    time.sleep(0.05)
    _pdi.moveTo(cx + 300, cy, duration=0.8)
    _pdi.mouseUp(button="middle")
    time.sleep(0.3)
    p2 = str(LOG_DIR / "audit_profile.png")
    capture_screen(p2)
    paths.append(p2)

    # Return zoom
    for _ in range(6):
        press_key("pagedown", wait=0.07)
    time.sleep(0.2)
    log("[audit] Captured: " + ", ".join(paths))
    return paths


# ── Command executor ──────────────────────────────────────────────────────────

def execute_command(cmd: dict[str, Any], log: Callable, dry: bool = False) -> None:
    """Translate one Gemini JSON decision into hardware input."""
    phase = cmd.get("current_phase", "")
    details = cmd.get("action_details", {})
    tab = cmd.get("target_ui_tab", "")
    keyword = cmd.get("search_keyword", "")
    log(f"[agent] phase={phase}  tab={tab}  reason={cmd.get('reasoning', '')[:80]}")

    if dry:
        log(f"[dry]   Would execute phase={phase} at details={details}")
        return

    # ── 1. Switch top-level UI tab if requested ───────────────────────────
    if tab and tab in PC2_UI.top_tabs:
        click_ui(PC2_UI.top_tabs[tab], wait=0.6)

    # ── 2. Dispatch per phase ─────────────────────────────────────────────

    if phase == "TERRAIN_SCULPT":
        tool = details.get("sculpt_mode", "push_up")
        activate_terrain_sculpt_tool(tool, log)
        # Drag across the target area
        sx_n, sy_n = details.get("start_coord", [0.5, 0.45])
        ex_n, ey_n = details.get("end_coord",   [0.55, 0.5])
        pattern = details.get("drag_pattern", "sinusoidal")
        sx, sy = _px(sx_n, sy_n)
        ex, ey = _px(ex_n, ey_n)
        human_drag(sx, sy, ex, ey, steps=40, pattern=pattern)

    elif phase == "TERRAIN_PAINT":
        texture = details.get("texture_name", "grass")
        activate_terrain_paint_texture(texture, log)
        sx_n, sy_n = details.get("start_coord", [0.5, 0.45])
        ex_n, ey_n = details.get("end_coord",   [0.55, 0.5])
        sx, sy = _px(sx_n, sy_n)
        ex, ey = _px(ex_n, ey_n)
        human_drag(sx, sy, ex, ey, steps=40, pattern="linear")

    elif phase == "TERRAIN_WATER":
        activate_water_tool(log)
        sx_n, sy_n = details.get("start_coord", [0.5, 0.5])
        ex_n, ey_n = details.get("end_coord",   [0.55, 0.55])
        sx, sy = _px(sx_n, sy_n)
        ex, ey = _px(ex_n, ey_n)
        human_drag(sx, sy, ex, ey, steps=40, pattern="spiral")

    elif phase == "ASSET_SEARCH":
        execute_search(keyword, log)

    elif phase == "OBJECT_PLACEMENT":
        coords = details.get("screen_coordinates_normalized", [0.5, 0.5])
        px, py = _px(coords[0], coords[1])
        rotations = int(details.get("rotation_clicks_required", 0))
        elevation = int(details.get("vertical_elevation_pixels", 0))
        snap = bool(details.get("enable_grid_snap", True))

        press_key("escape", wait=0.2)  # clear any active tool
        _pdi.moveTo(px, py, duration=0.2)
        time.sleep(0.1)

        if snap:
            press_key("f", wait=0.05)

        for _ in range(rotations):
            press_key("z", wait=0.12)

        if elevation != 0:
            _pdi.keyDown("shift")
            time.sleep(0.05)
            _pdi.moveTo(px, py - elevation, duration=0.3)
            _pdi.keyUp("shift")
            time.sleep(0.1)

        _pdi.click()
        time.sleep(0.4)
        log(f"[place] Placed object at ({px},{py}) rot={rotations} elev={elevation}")

    elif phase == "MAP_NAVIGATE":
        direction = details.get("direction", "forward")
        duration = float(details.get("duration", 1.5))
        pan_camera(direction, duration=duration, log=log)
        zoom_lvl = details.get("zoom_level", "none")
        if zoom_lvl == "in":
            zoom_camera("in", clicks=3, log=log)
        elif zoom_lvl == "out":
            zoom_camera("out", clicks=3, log=log)

    else:
        log(f"[agent] Unrecognised phase '{phase}' — skipping.")

    time.sleep(float(details.get("post_action_wait", 0.3)))


# ── Gemini vision client ──────────────────────────────────────────────────────

def _build_gemini_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


AUTONOMOUS_SCHEMA_DESCRIPTION = """\
You are an autonomous Planet Coaster 2 AI builder. You can see:
  1. A REFERENCE image (what the finished park should look like).
  2. The CURRENT game screen.
  3. A SPATIAL MEMORY map (E=empty, I=in_progress, C=complete).

Your job: decide the single best next action and output ONLY a JSON object
matching this exact schema:

{
  "current_phase": "<TERRAIN_SCULPT|TERRAIN_PAINT|TERRAIN_WATER|ASSET_SEARCH|OBJECT_PLACEMENT|MAP_NAVIGATE>",
  "reasoning": "<one sentence explaining your choice>",
  "target_ui_tab": "<terrain|paths|scenery|building|coasters|rides|null>",
  "search_keyword": "<asset name to search, e.g. 'castle wall 4m', or null>",
  "action_details": {
    "sculpt_mode": "<push_up|push_down|flatten|smooth|rugged — for TERRAIN_SCULPT>",
    "texture_name": "<texture name — for TERRAIN_PAINT>",
    "start_coord": [<norm_x 0-1>, <norm_y 0-1>],
    "end_coord":   [<norm_x 0-1>, <norm_y 0-1>],
    "drag_pattern": "<linear|sinusoidal|spiral>",
    "screen_coordinates_normalized": [<norm_x>, <norm_y>],
    "drag_end_coordinates_normalized": [<norm_x>, <norm_y>],
    "rotation_clicks_required": <int>,
    "vertical_elevation_pixels": <int>,
    "enable_grid_snap": <true|false>,
    "direction": "<forward|backward|left|right — for MAP_NAVIGATE>",
    "duration": <float seconds — for MAP_NAVIGATE>,
    "zoom_level": "<in|out|none — for MAP_NAVIGATE>",
    "post_action_wait": <float seconds>
  },
  "status": "<CONTINUE_IN_AREA|AREA_FINISHED>"
}

Rules:
- Choose TERRAIN_SCULPT to raise/lower/flatten land. Pick the best sculpt_mode.
- Choose TERRAIN_PAINT to apply textures (sand, grass, dirt, rock, cobblestone…).
- Choose TERRAIN_WATER to place water bodies.
- Choose ASSET_SEARCH to find and select a scenery/building piece from the menu.
- Choose OBJECT_PLACEMENT to drop the currently-selected piece at a coordinate.
- Choose MAP_NAVIGATE to pan/zoom the camera to a new area.
- All coordinates are normalised 0.0–1.0 relative to the screen.
- Set status=AREA_FINISHED when the current sector looks complete.
- Output ONLY the JSON object — no explanation, no markdown fences.
"""


def query_gemini(
    client,
    reference_path: Optional[str],
    current_screen_path: str,
    memory_string: str,
    model: str = "gemini-2.5-flash",
) -> dict[str, Any]:
    from google.genai import types

    parts = []
    if reference_path and Path(reference_path).exists():
        parts.append(types.Part.from_bytes(
            Path(reference_path).read_bytes(), mime_type="image/png"
        ))
    parts.append(types.Part.from_bytes(
        Path(current_screen_path).read_bytes(), mime_type="image/png"
    ))
    parts.append(
        f"{AUTONOMOUS_SCHEMA_DESCRIPTION}\n\nSPATIAL MEMORY:\n{memory_string}"
    )

    resp = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    raw = resp.text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    return json.loads(raw)


# ── Main autonomous loop ──────────────────────────────────────────────────────

def run_autonomous(
    reference_image: Optional[str],
    gemini_api_key: str,
    gemini_model: str = "gemini-2.5-flash",
    dry_run: bool = True,
    max_iterations: int = 200,
    log: Callable = print,
    stop: Callable[[], bool] = lambda: False,
) -> str:
    """
    Full autonomous build loop.

    Parameters
    ----------
    reference_image : path to the target reference image (park photo / blueprint)
    gemini_api_key  : Google Gemini API key
    gemini_model    : Gemini model name
    dry_run         : if True, decisions are logged but no input is sent
    max_iterations  : safety cap on number of Gemini queries
    log             : callable(str) for progress messages
    stop            : callable() -> bool to request halt

    Returns
    -------
    Summary string.
    """
    global ABORT
    ABORT = False

    if not dry_run:
        kill_thread = threading.Thread(target=_start_kill_switch, daemon=True)
        kill_thread.start()

    memory = ParkSpatialMemory()
    client = _build_gemini_client(gemini_api_key)

    log(f"[autonomous] Starting. Input backend: {_INPUT}. Dry-run: {dry_run}.")
    if reference_image:
        log(f"[autonomous] Reference image: {reference_image}")

    iteration = 0
    areas_completed = 0

    while iteration < max_iterations:
        if ABORT or stop():
            log("[autonomous] Stopped by user.")
            break

        iteration += 1
        log(f"\n─── Iteration {iteration}/{max_iterations} ───")

        # 1. Capture screen
        screen_path = capture_screen()

        # 2. Ask Gemini
        try:
            cmd = query_gemini(
                client,
                reference_path=reference_image,
                current_screen_path=screen_path,
                memory_string=memory.to_gemini_string(),
                model=gemini_model,
            )
        except Exception as exc:
            log(f"[gemini] Error: {exc}")
            time.sleep(2.0)
            continue

        # 3. Execute the action
        try:
            execute_command(cmd, log=log, dry=dry_run)
        except Exception as exc:
            log(f"[execute] Error: {exc}")

        # 4. Area-finished transition
        if cmd.get("status") == "AREA_FINISHED":
            cr, cc = memory.current_sector
            log(f"[memory] Sector ({cr},{cc}) finished. Running audit…")

            if not dry_run:
                try:
                    cinematic_audit(log)
                except Exception as exc:
                    log(f"[audit] {exc}")

            memory.register_complete(cr, cc)
            areas_completed += 1

            next_sec = memory.get_next_empty_sector()
            if next_sec is None:
                log("[autonomous] 🎉 All sectors complete! Park build finished.")
                break

            nr, nc = next_sec
            log(f"[memory] Navigating to next sector ({nr},{nc})…")
            if not dry_run:
                navigate_to_sector(nr, nc, memory.rows, memory.cols, cr, cc, log)
            memory.current_sector = (nr, nc)
            memory.mark_in_progress(nr, nc)

        time.sleep(1.2)

    summary = (
        f"Autonomous build completed.\n"
        f"Iterations: {iteration}\n"
        f"Areas completed: {areas_completed}\n"
        f"Grid status:\n{memory.to_gemini_string()}"
    )
    log(f"\n[autonomous] {summary}")
    return summary

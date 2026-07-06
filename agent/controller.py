"""Controller: execute a build plan in Planet Coaster via PC-level control.

This is the "hands" of the agent. It turns abstract, in-game-unit actions into
mouse / keyboard input using PyAutoGUI.

Important honesty note
----------------------
Planet Coaster exposes no API, so there is no ground-truth mapping from build
*units* to screen *pixels*. We approximate it with a calibrated affine
projection (``WorldProjector``): you point at two known ground positions once,
and every ``place_*`` action is projected through that mapping. It will never be
pixel-perfect - treat the automated build as a strong first pass you refine by
hand. Low-level ``click``/``drag``/``key`` actions use raw screen pixels and are
exact.

Safety
------
* ``dry_run=True`` (default) logs what *would* happen without moving the mouse.
* PyAutoGUI's fail-safe is enabled: slam the mouse into a screen corner to abort.
* A ``stop`` callable can be passed to interrupt between actions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .controls import PC2_DEFAULTS

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# menu name -> keyboard shortcut in Planet Coaster (defaults; override via cfg)
DEFAULT_HOTKEYS = {
    "Terrain": "t",
    "Paths": "p",
    "Scenery": "b",
    "Coasters": "r",
    "Rides": "y",
}


@dataclass
class WorldProjector:
    """Affine map from build units (x, y) to screen pixels, from 2 calibration points.

    Given two known unit positions and where they appear on screen, we derive a
    uniform scale + offset (assumes the camera is top-down-ish and un-rotated;
    good enough for a first-pass placement).
    """

    unit_a: tuple[float, float] = (0.0, 0.0)
    screen_a: tuple[int, int] = (400, 300)
    unit_b: tuple[float, float] = (100.0, 100.0)
    screen_b: tuple[int, int] = (1200, 800)

    def to_screen(self, ux: float, uy: float) -> tuple[int, int]:
        dux = (self.unit_b[0] - self.unit_a[0]) or 1.0
        duy = (self.unit_b[1] - self.unit_a[1]) or 1.0
        sx = (self.screen_b[0] - self.screen_a[0]) / dux
        sy = (self.screen_b[1] - self.screen_a[1]) / duy
        px = self.screen_a[0] + (ux - self.unit_a[0]) * sx
        py = self.screen_a[1] + (uy - self.unit_a[1]) * sy
        return int(round(px)), int(round(py))


@dataclass
class ControllerConfig:
    dry_run: bool = True
    action_delay: float = 0.35          # pause between actions (seconds)
    move_duration: float = 0.25         # mouse travel time
    hotkeys: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))
    controls: dict[str, str] = field(default_factory=lambda: dict(PC2_DEFAULTS))
    projector: WorldProjector = field(default_factory=WorldProjector)


def _pyautogui():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    return pyautogui


def execute_plan(
    plan: list[dict[str, Any]],
    memory: Any = None,
    config: ControllerConfig | None = None,
    stop: Callable[[], bool] | None = None,
    log: Callable[[str], None] | None = None,
    start_index: int = 0,
) -> dict[str, Any]:
    """Execute *plan* starting from *start_index*. Returns a summary dict {executed, skipped, errors}."""
    config = config or ControllerConfig()
    log = log or (lambda _msg: None)
    stop = stop or (lambda: False)

    gui = None if config.dry_run else _pyautogui()
    proj = config.projector

    executed = skipped = errors = 0

    for i in range(start_index, len(plan)):
        action = plan[i]
        if stop():
            log(f"[stop] interrupted before action #{i}")
            break

        atype = action.get("type")
        try:
            handled = _dispatch(action, atype, gui, proj, config, log)
            if handled:
                executed += 1
            else:
                skipped += 1
            if memory is not None:
                if hasattr(memory, "log_action"):
                    memory.log_action(action)
                if hasattr(memory, "save_state"):
                    memory.save_state(i + 1)
        except Exception as exc:  # keep going; a single bad node shouldn't kill the run
            errors += 1
            log(f"[error] action #{i} ({atype}): {exc}")

        if config.action_delay:
            time.sleep(config.action_delay if not config.dry_run else 0)

    # If build completed fully, clear the resume state
    if memory is not None and hasattr(memory, "clear_state"):
        if not stop() and (start_index + executed + skipped + errors >= len(plan)):
            memory.clear_state()

    summary = {
        "executed": executed,
        "skipped": skipped,
        "errors": errors,
        "total": len(plan) - start_index,
        "completed": (start_index + executed + skipped + errors) >= len(plan)
    }
    log(f"[done] {summary}")
    return summary


def _dispatch(action, atype, gui, proj, config, log) -> bool:
    """Perform one action. Returns True if it did something, False if it was a no-op."""
    dry = gui is None

    if atype == "note":
        log(f"[note] {action.get('text', '')}")
        return False

    if atype == "wait":
        secs = float(action.get("seconds", 1))
        log(f"[wait] {secs}s")
        if not dry:
            time.sleep(secs)
        return True

    if atype == "screenshot":
        _screenshot(dry, log)
        return True

    if atype == "select_menu":
        menu = action.get("menu", "")
        # Map standard menus to controls, otherwise fall back to hotkeys config
        menu_key_map = {
            "Terrain": config.controls.get("menu_terrain", "t"),
            "Paths": config.controls.get("menu_paths", "p"),
            "Scenery": config.controls.get("menu_scenery", "b"),
            "Coasters": config.controls.get("menu_coasters", "r"),
            "Rides": config.controls.get("menu_rides", "y"),
        }
        key = menu_key_map.get(menu) or config.hotkeys.get(menu)
        log(f"[menu] {menu} -> key '{key}'")
        if not dry and key:
            gui.press(key)
        return bool(key)

    if atype == "select_piece":
        log(f"[piece] select {action.get('name')}")
        return False  # piece selection is UI-specific; logged for the operator

    if atype == "key":
        key = action.get("key", "")
        log(f"[key] {key}")
        if not dry and key:
            gui.press(key)
        return True

    if atype == "click":
        x, y = int(action["x"]), int(action["y"])
        log(f"[click] ({x},{y})")
        if not dry:
            gui.moveTo(x, y, duration=config.move_duration)
            gui.click()
        return True

    if atype == "drag":
        x1, y1 = int(action["x1"]), int(action["y1"])
        x2, y2 = int(action["x2"]), int(action["y2"])
        log(f"[drag] ({x1},{y1})->({x2},{y2})")
        if not dry:
            gui.moveTo(x1, y1, duration=config.move_duration)
            gui.dragTo(x2, y2, duration=config.move_duration * 2, button="left")
        return True

    if atype == "rotate_camera":
        dx, dy = int(action.get("dx", 0)), int(action.get("dy", 0))
        log(f"[camera] rotate ({dx},{dy})")
        if not dry:
            gui.moveRel(dx, dy, duration=config.move_duration)
        return True

    if atype == "place_piece":
        px, py = proj.to_screen(float(action["x"]), float(action["y"]))
        log(f"[place] {action.get('name')} @unit({action['x']},{action['y']},{action['z']}) -> px({px},{py})")
        if not dry:
            gui.moveTo(px, py, duration=config.move_duration)
            gui.click()
        return True

    if atype == "place_track_node":
        px, py = proj.to_screen(float(action["x"]), float(action["y"]))
        log(f"[track] node @unit({action['x']},{action['y']},{action['z']}) bank={action['banking']} -> px({px},{py})")
        if not dry:
            gui.moveTo(px, py, duration=config.move_duration)
            gui.click()
        return True

    if atype == "sculpt_terrain":
        px, py = proj.to_screen(float(action["x"]), float(action["y"]))
        log(f"[terrain] sculpt @unit({action['x']},{action['y']}) str={action['strength']} r={action['radius']} -> px({px},{py})")
        if not dry:
            gui.moveTo(px, py, duration=config.move_duration)
            gui.click()
        return True

    if atype == "place_path":
        x1, y1 = proj.to_screen(float(action["x1"]), float(action["y1"]))
        x2, y2 = proj.to_screen(float(action["x2"]), float(action["y2"]))
        log(f"[path] w={action.get('width')} unit->px ({x1},{y1})->({x2},{y2})")
        if not dry:
            gui.moveTo(x1, y1, duration=config.move_duration)
            gui.dragTo(x2, y2, duration=config.move_duration * 2, button="left")
        return True

    if atype == "pan_camera":
        direction = action.get("direction", "").lower()
        duration = float(action.get("duration", 0.5))
        key_map = {
            "forward": config.controls.get("camera_move_forward", "w"),
            "backward": config.controls.get("camera_move_backward", "s"),
            "left": config.controls.get("camera_move_left", "a"),
            "right": config.controls.get("camera_move_right", "d")
        }
        key = key_map.get(direction)
        log(f"[camera] pan {direction} ({duration}s) -> key '{key}'")
        if not dry and key:
            gui.keyDown(key)
            time.sleep(duration)
            gui.keyUp(key)
        return bool(key)

    if atype == "zoom_camera":
        direction = action.get("direction", "").lower()
        clicks = int(action.get("clicks", 3))
        log(f"[camera] zoom {direction} ({clicks} clicks)")
        if not dry:
            scroll_amount = clicks if direction == "in" else -clicks
            gui.scroll(scroll_amount)
        return True

    if atype == "delete_object":
        key = config.controls.get("delete_object", "delete")
        log(f"[delete] remove object -> key '{key}'")
        if not dry and key:
            gui.press(key)
        return bool(key)

    log(f"[skip] unknown action type: {atype}")
    return False


def _screenshot(dry: bool, log) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"shot_{int(time.time())}.png"
    if dry:
        log(f"[screenshot] (dry-run) would save {path.name}")
        return
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            img = sct.grab(sct.monitors[1])
            mss.tools.to_png(img.rgb, img.size, output=str(path))
        log(f"[screenshot] saved {path.name}")
    except Exception as exc:
        log(f"[screenshot] failed: {exc}")

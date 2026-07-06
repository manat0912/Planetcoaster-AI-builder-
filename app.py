#!/usr/bin/env python3
"""PlanetCoaster AI Builder - Gradio front end.

Pipeline:
    blueprints -> [vision] layout -> [scan] in-game dims -> [planner] build plan
    -> [controller] execute in Planet Coaster (dry-run by default).

Everything runs locally through Pinokio; the controller only moves your mouse /
keyboard when you turn OFF dry-run AND Planet Coaster is the focused window.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

import gradio as gr

from agent import dimensions, planner, vision
from agent.controller import ControllerConfig, WorldProjector, execute_plan
from agent.memory import AgentMemory
from agent.model import PROVIDER_MODELS, load_config, save_config
from agent.controls import scan_game_directory, PC2_DEFAULTS

BLUEPRINT_DIR = Path(__file__).resolve().parent / "blueprints"
BLUEPRINT_DIR.mkdir(exist_ok=True)


def run_scan_folder(folder_path):
    res = scan_game_directory(folder_path)
    status_md = f"### Scan Results\n- **Status**: {res['status']}\n- **Detected Game**: {res['game_version']}\n"
    if res['config_files_found']:
        status_md += f"- **Config Files Found**:\n"
        for f in res['config_files_found']:
            status_md += f"  - `{f}`\n"
    
    ctrls = res['controls']
    return (
        status_md,
        res['game_version'],
        ctrls.get("camera_move_forward", "w"),
        ctrls.get("camera_move_backward", "s"),
        ctrls.get("camera_move_left", "a"),
        ctrls.get("camera_move_right", "d"),
        ctrls.get("camera_zoom_in", "pageup"),
        ctrls.get("camera_zoom_out", "pagedown"),
        ctrls.get("menu_terrain", "t"),
        ctrls.get("menu_paths", "p"),
        ctrls.get("menu_scenery", "b"),
        ctrls.get("menu_coasters", "r"),
        ctrls.get("menu_rides", "y"),
        ctrls.get("delete_object", "delete"),
        ctrls.get("place_object", "left_click"),
        ctrls.get("cancel_action", "escape"),
        ctrls.get("rotate_object", "z"),
        ctrls.get("height_adj", "shift"),
    )


def save_custom_keybinds(
    folder_path, game_version, forward, backward, left, right, zoom_in, zoom_out,
    terrain, paths, scenery, coasters, rides, delete_obj, place_obj, cancel, rotate, height_adj
):
    cfg = load_config()
    controls_dict = {
        "camera_move_forward": forward,
        "camera_move_backward": backward,
        "camera_move_left": left,
        "camera_move_right": right,
        "camera_zoom_in": zoom_in,
        "camera_zoom_out": zoom_out,
        "menu_terrain": terrain,
        "menu_paths": paths,
        "menu_scenery": scenery,
        "menu_coasters": coasters,
        "menu_rides": rides,
        "delete_object": delete_obj,
        "place_object": place_obj,
        "cancel_action": cancel,
        "rotate_object": rotate,
        "height_adj": height_adj,
    }
    cfg["game_folder"] = folder_path
    cfg["game_version"] = game_version
    cfg["controls"] = controls_dict
    save_config(cfg)
    return "Custom controls and keybinds saved successfully to config.json."


def load_controls_ui():
    cfg = load_config()
    folder_path = cfg.get("game_folder", "")
    game_version = cfg.get("game_version", "Planet Coaster 2")
    ctrls = cfg.get("controls", {})
    if not ctrls:
        ctrls = dict(PC2_DEFAULTS)
        
    return (
        folder_path,
        game_version,
        ctrls.get("camera_move_forward", "w"),
        ctrls.get("camera_move_backward", "s"),
        ctrls.get("camera_move_left", "a"),
        ctrls.get("camera_move_right", "d"),
        ctrls.get("camera_zoom_in", "pageup"),
        ctrls.get("camera_zoom_out", "pagedown"),
        ctrls.get("menu_terrain", "t"),
        ctrls.get("menu_paths", "p"),
        ctrls.get("menu_scenery", "b"),
        ctrls.get("menu_coasters", "r"),
        ctrls.get("menu_rides", "y"),
        ctrls.get("delete_object", "delete"),
        ctrls.get("place_object", "left_click"),
        ctrls.get("cancel_action", "escape"),
        ctrls.get("rotate_object", "z"),
        ctrls.get("height_adj", "shift"),
    )


def check_resume_status():
    memory = AgentMemory()
    state = memory.load_state()
    if not state:
        return "No saved build in cache. Start a new build below."
    plan_len = len(state.get("plan", []))
    idx = state.get("current_index", 0)
    timestamp = state.get("timestamp", 0)
    import datetime
    time_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    return f"**Saved Build State**: Step **{idx}** of **{plan_len}** (Saved: {time_str}). Ready to resume!"


def run_resume_build(dry_run, ax, ay, aux, auy, bx, by, bux, buy, action_delay):
    memory = AgentMemory()
    state = memory.load_state()
    if not state:
        return "No saved build progress found to resume. Please generate a new plan and build."
    
    plan = state.get("plan")
    start_index = state.get("current_index", 0)
    layout = state.get("layout", {})
    dims = state.get("ingame_dims", {})
    
    if not plan:
        return "Loaded state has no build plan."
        
    memory.save_layout(layout)
    memory.save_dims(dims)
    memory.save_plan(plan)
    
    projector = WorldProjector(
        unit_a=(float(aux), float(auy)), screen_a=(int(ax), int(ay)),
        unit_b=(float(bux), float(buy)), screen_b=(int(bx), int(by)),
    )
    
    cfg = load_config()
    custom_controls = cfg.get("controls", {})
    if custom_controls:
        config = ControllerConfig(
            dry_run=bool(dry_run),
            action_delay=float(action_delay),
            projector=projector,
            controls=custom_controls
        )
    else:
        config = ControllerConfig(dry_run=bool(dry_run), action_delay=float(action_delay), projector=projector)
        
    memory.log(f"[resume] starting from step #{start_index} (of {len(plan)})")
    summary = execute_plan(plan, memory=memory, config=config, log=memory.log, start_index=start_index)
    header = f"RESUMED DRY RUN (starting from step {start_index}) - " if dry_run else f"RESUMED LIVE BUILD (starting from step {start_index}) - "
    return header + json.dumps(summary) + "\n\n" + memory.text_log()


# ── settings ─────────────────────────────────────────────────────────────────
def load_settings():
    cfg = load_config()
    provider = cfg.get("provider", "Anthropic Claude")
    return (
        provider,
        cfg.get("model", (PROVIDER_MODELS.get(provider) or [""])[0]),
        cfg.get("anthropic_api_key", ""),
        cfg.get("gemini_api_key", ""),
        cfg.get("openai_api_key", ""),
        cfg.get("openai_base_url", "https://api.openai.com/v1"),
    )


def refresh_models(provider):
    models = PROVIDER_MODELS.get(provider, [])
    value = models[0] if models else ""
    return gr.update(choices=models, value=value)


def save_settings(provider, model, anthropic_key, gemini_key, openai_key, openai_base):
    cfg = load_config()
    cfg.update({
        "provider": provider,
        "model": model,
        "anthropic_api_key": anthropic_key,
        "gemini_api_key": gemini_key,
        "openai_api_key": openai_key,
        "openai_base_url": openai_base,
    })
    save_config(cfg)
    return "Settings saved."


# ── pipeline steps ─────────────────────────────────────────────────────────--
def _save_uploads(files) -> list[str]:
    paths = []
    for f in files or []:
        src = Path(f.name if hasattr(f, "name") else f)
        dst = BLUEPRINT_DIR / src.name
        dst.write_bytes(src.read_bytes())
        paths.append(str(dst))
    return paths


def run_extract(files, real_park_prompt):
    try:
        paths = _save_uploads(files)
        if not paths:
            return None, "Upload at least one blueprint / map / schematic image first."
        layout = vision.extract_layout(paths, real_park_prompt=real_park_prompt)
        return layout, json.dumps(layout, indent=2)
    except Exception as exc:
        return None, f"Extraction failed: {exc}\n\n{traceback.format_exc()}"


def run_scan(dim_mode, width_units, height_units, meters_per_unit):
    try:
        if dim_mode == "Manual calibration":
            dims = dimensions.manual_dimensions(int(width_units), int(height_units), float(meters_per_unit))
        else:
            dims = dimensions.scan_ingame_dimensions_vision()
        return dims, json.dumps(dims, indent=2)
    except Exception as exc:
        return None, f"Scan failed: {exc}"


def run_plan(layout, dims, plan_mode):
    try:
        if not layout:
            return None, "Run 'Extract layout' first."
        if not dims:
            return None, "Run 'Scan in-game area' first."
        if plan_mode == "Fast preview (no API)":
            plan = planner.layout_to_outline_plan(layout, dims)
        else:
            plan = planner.generate_plan(layout, dims)
        return plan, json.dumps(plan, indent=2)
    except Exception as exc:
        return None, f"Planning failed: {exc}"


def run_build(plan, layout, dims, dry_run, ax, ay, aux, auy, bx, by, bux, buy, action_delay):
    if not plan:
        return "Generate a plan first."
    memory = AgentMemory()
    memory.save_layout(layout or {})
    memory.save_dims(dims or {})
    memory.save_plan(plan or [])
    projector = WorldProjector(
        unit_a=(float(aux), float(auy)), screen_a=(int(ax), int(ay)),
        unit_b=(float(bux), float(buy)), screen_b=(int(bx), int(by)),
    )
    cfg = load_config()
    custom_controls = cfg.get("controls", {})
    if custom_controls:
        config = ControllerConfig(
            dry_run=bool(dry_run),
            action_delay=float(action_delay),
            projector=projector,
            controls=custom_controls
        )
    else:
        config = ControllerConfig(dry_run=bool(dry_run), action_delay=float(action_delay), projector=projector)
    summary = execute_plan(plan, memory=memory, config=config, log=memory.log)
    header = "DRY RUN (no input sent) - " if dry_run else "LIVE BUILD - "
    return header + json.dumps(summary) + "\n\n" + memory.text_log()



# ── UI ───────────────────────────────────────────────────────────────────────
CSS = """
.main-title { text-align:center; margin-bottom:0.1em; }
.sub-title  { text-align:center; color:#666; margin-top:0; margin-bottom:1em; }
"""

with gr.Blocks(title="PlanetCoaster AI Builder") as demo:
    gr.Markdown("# PlanetCoaster AI Builder", elem_classes="main-title")
    gr.Markdown(
        "Upload real park blueprints, extract the layout with a vision model, "
        "scale it to your in-game plot, and build it in Planet Coaster.",
        elem_classes="sub-title",
    )

    layout_state = gr.State()
    dims_state = gr.State()
    plan_state = gr.State()

    with gr.Tabs():
        # ── Build ────────────────────────────────────────────────────────────
        with gr.Tab("Build") as build_tab:
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 1. Blueprints")
                    files = gr.File(
                        label="Blueprints / maps / coaster schematics / photos",
                        file_count="multiple",
                        file_types=["image"],
                    )
                    real_park_prompt = gr.Textbox(
                        label="Real-world scale & dimensions prompt / guidance (optional)",
                        placeholder="e.g., 'The real park is 1200 meters wide by 800 meters high. The main entrance is on the south side.'",
                        lines=3,
                    )
                    extract_btn = gr.Button("1. Extract layout", variant="primary")

                    gr.Markdown("### 2. In-game area")
                    dim_mode = gr.Radio(
                        ["Manual calibration", "Vision scan (screenshot game)"],
                        value="Manual calibration",
                        label="How to measure the buildable area",
                    )
                    width_units = gr.Number(value=200, label="Width (grid units)")
                    height_units = gr.Number(value=150, label="Height (grid units)")
                    meters_per_unit = gr.Number(value=4.0, label="Meters per grid unit")
                    scan_btn = gr.Button("2. Scan in-game area")

                    gr.Markdown("### 3. Plan")
                    plan_mode = gr.Radio(
                        ["Full build (model)", "Fast preview (no API)"],
                        value="Fast preview (no API)",
                        label="Plan type",
                    )
                    plan_btn = gr.Button("3. Generate build plan")

                with gr.Column(scale=2):
                    layout_out = gr.Code(label="Extracted layout (JSON)", language="json")
                    dims_out = gr.Code(label="In-game dimensions (JSON)", language="json")
                    plan_out = gr.Code(label="Build plan (JSON)", language="json")

            gr.Markdown("### 4. Build in Planet Coaster")
            gr.Markdown(
                "Keep **Dry run** ON to preview the action log without touching your mouse. "
                "Turn it OFF only with Planet Coaster open, focused and in build mode. "
                "Fail-safe: slam the mouse into a screen corner to abort."
            )
            with gr.Row():
                dry_run = gr.Checkbox(value=True, label="Dry run (recommended)")
                action_delay = gr.Number(value=0.35, label="Delay between actions (s)")
            with gr.Row():
                build_btn = gr.Button("4. Build", variant="primary", scale=2)
                resume_btn = gr.Button("Resume Last Build", variant="secondary", scale=1)
            resume_status = gr.Markdown("### Resume Status\nChecking saved build cache...")
            build_out = gr.Textbox(label="Build log", lines=16)

            # wiring
            extract_btn.click(run_extract, inputs=[files, real_park_prompt], outputs=[layout_state, layout_out])
            scan_btn.click(
                run_scan,
                inputs=[dim_mode, width_units, height_units, meters_per_unit],
                outputs=[dims_state, dims_out],
            )
            plan_btn.click(run_plan, inputs=[layout_state, dims_state, plan_mode], outputs=[plan_state, plan_out])

        # ── Calibration ────────────────────────────────────────────────────---
        with gr.Tab("Calibration"):
            gr.Markdown("""
### World -> screen calibration
Planet Coaster has no API, so placement uses an approximate affine mapping from
build **units** to screen **pixels**. Provide two reference points: pick two
known ground positions in your park (in units) and where they appear on screen
(in pixels). Tip: use a screen ruler / the coordinates overlay to read pixels.
""")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Point A**")
                    aux = gr.Number(value=0, label="Unit X (A)")
                    auy = gr.Number(value=0, label="Unit Y (A)")
                    ax = gr.Number(value=400, label="Screen X px (A)")
                    ay = gr.Number(value=300, label="Screen Y px (A)")
                with gr.Column():
                    gr.Markdown("**Point B**")
                    bux = gr.Number(value=100, label="Unit X (B)")
                    buy = gr.Number(value=100, label="Unit Y (B)")
                    bx = gr.Number(value=1200, label="Screen X px (B)")
                    by = gr.Number(value=800, label="Screen Y px (B)")

            build_btn.click(
                run_build,
                inputs=[plan_state, layout_state, dims_state, dry_run, ax, ay, aux, auy, bx, by, bux, buy, action_delay],
                outputs=[build_out],
            ).then(check_resume_status, outputs=resume_status)

            resume_btn.click(
                run_resume_build,
                inputs=[dry_run, ax, ay, aux, auy, bx, by, bux, buy, action_delay],
                outputs=[build_out],
            ).then(check_resume_status, outputs=resume_status)
        # ── Controls & Scanner ───────────────────────────────────────────────
        with gr.Tab("Controls & Scanner") as controls_tab:
            gr.Markdown("### Game Folder & Controls Scanner")
            gr.Markdown(
                "Point the scanner to your game installation directory or your Saved Games settings folder. "
                "The agent will automatically identify the game version (Planet Coaster 1 vs 2) and parse "
                "any control binding configuration XMLs (e.g. `Controls_remote.config.xml`)."
            )
            with gr.Row():
                game_folder = gr.Textbox(
                    label="Game Folder or Saved Games Config Path",
                    placeholder="e.g. C:\\Users\\[Username]\\Saved Games\\Frontier Developments\\Planet Coaster 2",
                    scale=4
                )
                scan_btn = gr.Button("Scan Game Folder", variant="primary", scale=1)
                
            scan_status = gr.Markdown("### Scan Results\n- **Status**: Not scanned yet.\n- **Detected Game**: Planet Coaster 2 (Default)")
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### Camera Mappings")
                    ctrl_game_version = gr.Textbox(label="Detected Game Version", value="Planet Coaster 2", interactive=False)
                    ctrl_forward = gr.Textbox(label="Move Forward", value="w")
                    ctrl_backward = gr.Textbox(label="Move Backward", value="s")
                    ctrl_left = gr.Textbox(label="Move Left", value="a")
                    ctrl_right = gr.Textbox(label="Move Right", value="d")
                    ctrl_zoom_in = gr.Textbox(label="Zoom In", value="pageup")
                    ctrl_zoom_out = gr.Textbox(label="Zoom Out", value="pagedown")
                with gr.Column():
                    gr.Markdown("#### Build Menu Mappings")
                    ctrl_terrain = gr.Textbox(label="Terrain Menu", value="t")
                    ctrl_paths = gr.Textbox(label="Paths Menu", value="p")
                    ctrl_scenery = gr.Textbox(label="Scenery/Build Menu", value="b")
                    ctrl_coasters = gr.Textbox(label="Coasters Menu", value="r")
                    ctrl_rides = gr.Textbox(label="Rides Menu", value="y")
                with gr.Column():
                    gr.Markdown("#### Object Actions")
                    ctrl_delete = gr.Textbox(label="Delete Object", value="delete")
                    ctrl_place = gr.Textbox(label="Place Object (Mouse)", value="left_click")
                    ctrl_cancel = gr.Textbox(label="Cancel/Deselect", value="escape")
                    ctrl_rotate = gr.Textbox(label="Rotate Object", value="z")
                    ctrl_height = gr.Textbox(label="Adjust Height", value="shift")
                    
            save_ctrl_btn = gr.Button("Save Keybind Mappings", variant="primary")
            save_ctrl_status = gr.Textbox(label="", interactive=False, show_label=False)

            # Scan wiring
            scan_btn.click(
                run_scan_folder,
                inputs=[game_folder],
                outputs=[
                    scan_status, ctrl_game_version,
                    ctrl_forward, ctrl_backward, ctrl_left, ctrl_right,
                    ctrl_zoom_in, ctrl_zoom_out,
                    ctrl_terrain, ctrl_paths, ctrl_scenery, ctrl_coasters, ctrl_rides,
                    ctrl_delete, ctrl_place, ctrl_cancel, ctrl_rotate, ctrl_height
                ]
            )
            # Save wiring
            save_ctrl_btn.click(
                save_custom_keybinds,
                inputs=[
                    game_folder, ctrl_game_version,
                    ctrl_forward, ctrl_backward, ctrl_left, ctrl_right,
                    ctrl_zoom_in, ctrl_zoom_out,
                    ctrl_terrain, ctrl_paths, ctrl_scenery, ctrl_coasters, ctrl_rides,
                    ctrl_delete, ctrl_place, ctrl_cancel, ctrl_rotate, ctrl_height
                ],
                outputs=[save_ctrl_status]
            )
            # Tab selection load wiring
            controls_tab.select(
                load_controls_ui,
                outputs=[
                    game_folder, ctrl_game_version,
                    ctrl_forward, ctrl_backward, ctrl_left, ctrl_right,
                    ctrl_zoom_in, ctrl_zoom_out,
                    ctrl_terrain, ctrl_paths, ctrl_scenery, ctrl_coasters, ctrl_rides,
                    ctrl_delete, ctrl_place, ctrl_cancel, ctrl_rotate, ctrl_height
                ]
            )

        # ── Settings ─────────────────────────────────────────────────────────
        with gr.Tab("Settings") as settings_tab:
            gr.Markdown("### Model provider")
            provider = gr.Dropdown(
                choices=list(PROVIDER_MODELS.keys()),
                value="Anthropic Claude",
                label="Provider",
            )
            model = gr.Dropdown(
                choices=PROVIDER_MODELS["Anthropic Claude"],
                value=PROVIDER_MODELS["Anthropic Claude"][0],
                label="Model",
            )
            gr.Markdown("### API keys (stored locally in config.json)")
            anthropic_key = gr.Textbox(label="Anthropic API key", type="password")
            gemini_key = gr.Textbox(label="Google Gemini API key", type="password")
            openai_key = gr.Textbox(label="OpenAI API key", type="password")
            openai_base = gr.Textbox(label="OpenAI base URL", value="https://api.openai.com/v1")
            save_btn = gr.Button("Save settings", variant="primary")
            save_status = gr.Textbox(label="", interactive=False, show_label=False)

            provider.change(refresh_models, inputs=provider, outputs=model)
            save_btn.click(
                save_settings,
                inputs=[provider, model, anthropic_key, gemini_key, openai_key, openai_base],
                outputs=save_status,
            )
            settings_tab.select(
                load_settings,
                outputs=[provider, model, anthropic_key, gemini_key, openai_key, openai_base],
            )

        # ── Help ─────────────────────────────────────────────────────────────
        with gr.Tab("Help"):
            gr.Markdown("""
## What this does
1. **Extract layout** - a vision model (Claude / Gemini / GPT-4o) reads your
   uploaded blueprints, maps and coaster schematics and returns a normalized JSON
   layout (zones, paths, buildings, coaster track, rides).
2. **Scan in-game area** - measure the buildable plot in grid units, manually or
   by screenshotting the game.
3. **Generate build plan** - the layout is uniformly scaled to *fit* your plot,
   then turned into an ordered list of in-game build actions.
4. **Build** - the controller drives Planet Coaster with mouse/keyboard.

## Honest limitations
- Planet Coaster has **no API/mod hooks**, so placement uses an approximate
  units->pixels calibration. Expect a strong first pass you refine by hand, not a
  pixel-perfect clone.
- Always test with **Dry run** first. Live mode moves your real mouse/keyboard.
- Works for Planet Coaster **1 and 2**; menu hotkeys may differ - adjust them in
  `agent/controller.py` (`DEFAULT_HOTKEYS`).

## Getting API keys
- **Claude**: https://console.anthropic.com/
- **Gemini**: https://aistudio.google.com/apikey
- **OpenAI**: https://platform.openai.com/api-keys
""")

    demo.load(check_resume_status, outputs=resume_status)
    build_tab.select(check_resume_status, outputs=resume_status)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, css=CSS)

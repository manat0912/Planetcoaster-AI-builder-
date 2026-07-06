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

BLUEPRINT_DIR = Path(__file__).resolve().parent / "blueprints"
BLUEPRINT_DIR.mkdir(exist_ok=True)


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


def run_extract(files):
    try:
        paths = _save_uploads(files)
        if not paths:
            return None, "Upload at least one blueprint / map / schematic image first."
        layout = vision.extract_layout(paths)
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


def run_build(plan, dry_run, ax, ay, aux, auy, bx, by, bux, buy, action_delay):
    if not plan:
        return "Generate a plan first."
    memory = AgentMemory()
    projector = WorldProjector(
        unit_a=(float(aux), float(auy)), screen_a=(int(ax), int(ay)),
        unit_b=(float(bux), float(buy)), screen_b=(int(bx), int(by)),
    )
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
        with gr.Tab("Build"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 1. Blueprints")
                    files = gr.File(
                        label="Blueprints / maps / coaster schematics / photos",
                        file_count="multiple",
                        file_types=["image"],
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
            build_btn = gr.Button("4. Build", variant="primary")
            build_out = gr.Textbox(label="Build log", lines=16)

            # wiring
            extract_btn.click(run_extract, inputs=[files], outputs=[layout_state, layout_out])
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
                inputs=[plan_state, dry_run, ax, ay, aux, auy, bx, by, bux, buy, action_delay],
                outputs=[build_out],
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

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, css=CSS)

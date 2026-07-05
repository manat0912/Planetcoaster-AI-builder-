---
name: testing-pipeline
description: End-to-end test the PlanetCoaster AI Builder Gradio pipeline (blueprint → vision extract → scale-to-fit → plan → dry-run build). Use when verifying UI or agent changes.
---

# Testing the PlanetCoaster AI Builder pipeline

## What the app does
Gradio app (`app.py`, port 7860) with a 4-stage Build tab:
1. Extract layout — `vision.extract_layout(paths)` → **always calls the vision model** (needs an API key).
2. Scan in-game area — `dimensions.manual_dimensions()` (Manual) or vision scan.
3. Generate plan — "Fast preview (no API)" = `planner.layout_to_outline_plan` (deterministic, no API); "Full build (model)" = `generate_plan` (needs API).
4. Build — `controller.execute_plan`, **dry-run ON by default** (logs actions, sends no input).

## Key gotcha: even "no API" needs a layout
The Fast-preview plan is API-free, but it still needs a `layout`, and the only way to
produce one is stage 1 (Extract), which **always** calls the vision model. So any
real end-to-end UI test needs one working vision API key. To test with zero API,
you must fabricate a layout dict and call `planner`/`controller` directly in Python.

## Setup
```bash
cd <repo> && python3 -m venv env && ./env/bin/pip install -r requirements.txt
```
Config lives in `config.json` (gitignored) or env vars `ANTHROPIC_API_KEY` /
`GEMINI_API_KEY` / `OPENAI_API_KEY`. Write `config.json` with keys:
`provider` ("Google Gemini" | "Anthropic" | "OpenAI-Compatible"), `model`,
`<provider>_api_key`, `max_output_tokens`, `temperature`.

## Known issue: stale default model names
`agent/model.py` `PROVIDER_MODELS` may list model names that the provider has since
retired (e.g. Gemini `gemini-2.0-flash`, `*-preview-05-*` → HTTP 404 "no longer
available"). If extraction 404s, **list live models first** and pick a current one:
```python
from agent.model import load_config
from google import genai
c = genai.Client(api_key=load_config()["gemini_api_key"])
print([m.name for m in c.models.list()])
```
`gemini-2.5-flash` worked as of this writing. The Settings dropdown only offers
names in `PROVIDER_MODELS`, but actual calls read `config.json`'s `model`, so you
can set a working model there regardless of the dropdown.

## Fast verification (shell, no UI)
```python
from agent import vision, planner
from agent.schema import validate_plan
layout = vision.extract_layout(["blueprints/sample_park_blueprint.png"])
dims = {"width_units":200,"height_units":150,"meters_per_unit":4.0}
plan = planner.layout_to_outline_plan(layout, dims)
assert validate_plan(plan) == []          # no schema problems
assert all(0 <= a.get("x",0) <= dims["width_units"] for a in plan if "x" in a)
```

## UI test tips
- Generate a synthetic blueprint PNG with PIL (labeled zones, a colored coaster
  loop, buildings, a scale note like "approx 900m x 650m") so you can assert the
  model actually read title/scale/zones rather than returning a stub.
- Gradio file upload opens a GTK dialog: click the upload area, then `Ctrl+L` and
  type the absolute path, `Return`.
- The JSON output panels get very tall; the Build section sits far below — scroll
  a lot (or collapse panels) to reach the "4. Build" button.
- Gemini extraction can take 20–40s; poll with waits rather than assuming failure.
- Assert on the dry-run log: `DRY RUN (no input sent) - {"executed":N,...,"errors":0,...}`.

## Cannot test here
The live in-game PyAutoGUI build needs Windows + Planet Coaster + a display. On a
headless Linux VM only the dry-run action log is verifiable.

## Cleanup / secrets
API keys are provided per-session. Store only in gitignored `config.json`; after
testing remove it and revert any temp edits, then grep the repo tree + `logs/` to
confirm the key string is gone.

## Devin Secrets Needed
- One of `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` (vision-capable) — required for the Extract stage and full-build plans.

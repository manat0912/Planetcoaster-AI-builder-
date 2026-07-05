# PlanetCoaster AI Builder

A [Pinokio](https://pinokio.computer) app that reads real theme-park blueprints,
maps and coaster schematics with a closed-source vision model (Claude / Gemini /
GPT-4o), scales the park to fit your in-game plot, and builds it in **Planet
Coaster 1 & 2** via PC-level control (mouse + keyboard).

> **Reality check.** Planet Coaster exposes no API or modding hooks, so the agent
> drives the game like a human player. Placement uses an approximate
> units-to-pixels calibration, so treat the automated build as a strong first
> pass you refine by hand — not a pixel-perfect clone. Always test in **Dry run**
> first.

## Pipeline

```
blueprints ──▶ [vision]  ──▶ layout (normalized JSON)
layout     ──▶ [scan]    ──▶ in-game buildable dimensions
layout+dims──▶ [planner] ──▶ scaled build plan (in-game units)
plan       ──▶ [controller] ──▶ Planet Coaster (PyAutoGUI)
```

## Install (Pinokio)

1. In Pinokio, **Download from URL**:
   `https://github.com/manat0912/Planetcoaster-AI-builder-`
2. Click **Install** (creates a Python venv and installs `requirements.txt`).
3. Click **Start** and open the Web UI.
4. In **Settings**, choose a provider and paste your API key.

## Usage

1. **Build tab → Extract layout**: upload blueprints / satellite maps / coaster
   schematics / reference photos.
2. **Scan in-game area**: enter your plot size in grid units (or screenshot the
   game for a vision estimate).
3. **Generate build plan**: *Fast preview* is deterministic and needs no API;
   *Full build* uses the model to produce detailed actions.
4. **Calibration tab**: set the two unit↔pixel reference points.
5. **Build**: keep **Dry run** on to preview the action log; turn it off with
   Planet Coaster focused and in build mode to actually build. Fail-safe: slam
   the mouse into a screen corner to abort.

## Pinokio scripts

| Script | Purpose |
|--------|---------|
| `install.js` | Create venv `env`, install `requirements.txt`. |
| `start.js` | Launch the Gradio app (`app.py`), capture its URL. |
| `update.js` | `git pull` + reinstall requirements. |
| `reset.js` | Remove the venv to revert to a pre-install state. |
| `link.js` | Deduplicate venv files to save disk. |
| `pinokio.js` | Menu / state machine for the Pinokio launcher. |

## Layout of the repo

```
├── pinokio.json / pinokio.js        # Pinokio manifest + menu
├── install.js / start.js / update.js / reset.js / link.js
├── app.py                           # Gradio UI + pipeline orchestration
├── requirements.txt
└── agent/
    ├── model.py        # Claude / Gemini / OpenAI client (text + vision, JSON)
    ├── vision.py       # blueprints -> normalized layout JSON
    ├── dimensions.py   # scan buildable area (manual or vision)
    ├── planner.py      # scale-to-fit + build plan (model or deterministic)
    ├── controller.py   # execute plan via PyAutoGUI (dry-run by default)
    ├── memory.py       # run state + logging
    └── schema.py       # layout / action schemas + validators
```

## Requirements

- Windows (Planet Coaster is a Windows game) with the game installed.
- Python 3.10+ (Pinokio manages the venv).
- An API key for Claude, Gemini, or an OpenAI-compatible endpoint.

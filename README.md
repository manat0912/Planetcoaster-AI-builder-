# PlanetCoaster AI Builder

A [Pinokio](https://pinokio.computer) app that reads real theme-park blueprints,
maps and coaster schematics with a vision model (Claude / Gemini / GPT-4o),
scales the park to fit your in-game plot, and builds it in **Planet Coaster 1 & 2**
via PC-level control (mouse + keyboard) — with a fully **autonomous AI mode**
that sees the live game screen and makes every decision on its own.

> **Reality check.** Planet Coaster exposes no API or modding hooks, so the agent
> drives the game like a human player using hardware-level mouse and keyboard input.
> Placement uses an approximate units-to-pixels calibration, so treat the automated
> build as a strong first pass you refine by hand — not a pixel-perfect clone.
> Always test in **Dry run** first.

---

## ✨ Features

### 🗺️ Guided Build Mode (original)
- Upload real park blueprints, satellite maps, or coaster schematics
- Vision model extracts a normalised park layout (zones, paths, rides, water)
- Planner scales and orders build actions to fit your in-game plot
- Controller executes the plan step by step with PyDirectInput hardware input

### 🤖 Fully Autonomous Agent Mode (new)
- **Zero operator input** once started — Gemini sees the live game and decides everything
- Captures the screen every ~1.5 seconds and sends it to Gemini alongside your reference image
- Gemini chooses the right build phase automatically:

| Phase | What the agent does on its own |
|---|---|
| `TERRAIN_SCULPT` | Opens Terrain → clicks the correct tool (push up/down/flatten/smooth) → drags with sinusoidal or spiral mouse paths |
| `TERRAIN_PAINT` | Switches to the paint sub-tab → selects the matching texture slot (grass/sand/dirt/rock/cobblestone/jungle…) → paints the area |
| `TERRAIN_WATER` | Opens the water sub-tab → spiral-drags to form a natural lake or river basin |
| `ASSET_SEARCH` | Clears the search bar → types the asset keyword → presses Enter → clicks the first result |
| `OBJECT_PLACEMENT` | Escapes any active tool → navigates to target → rotates with Z key → adjusts height with Shift+drag → places |
| `MAP_NAVIGATE` | Holds WASD to pan the camera → zooms with Page Up/Down → orbits for audit sweeps |

- **Spatial memory grid** (8×8) tracks which park sectors are built — the agent never re-builds a finished area
- **Cinematic audit sweeps** after each zone: camera orbits the finished area so Gemini can verify quality
- **ESC / Q kill-switch**: a background thread monitors the keyboard — press either key to instantly halt and release all inputs
- Streams a live decision log back to the Gradio UI while running

---

## 🚀 Install (Pinokio)

1. In Pinokio, click **Download from URL**:
   `https://github.com/manat0912/Planetcoaster-AI-builder-`
2. Click **Install** — creates a Python venv and installs all dependencies including `pydirectinput`, `numpy`, `opencv-python`, and `keyboard`.
3. Click **Start** and open the Web UI.
4. In **Settings**, choose a provider and paste your API key.
   - For the Autonomous Agent you **must** set a **Gemini** API key.

---

## 📖 Usage

### Guided Build Mode
1. **Build tab → Extract layout**: upload blueprints / satellite maps / reference photos.
2. **Scan in-game area**: enter your plot size in grid units (or screenshot the game for a vision estimate).
3. **Generate build plan**: *Fast preview* is deterministic and needs no API; *Full build* uses the model to produce detailed actions.
4. **Calibration tab**: set the two unit↔pixel reference points so the projector knows where your park is on screen.
5. **Build**: keep **Dry run ON** to preview the action log; turn it OFF with Planet Coaster focused and in build mode to actually build.

### 🤖 Autonomous Agent Mode
1. Open Planet Coaster 2 and load your park (flat terrain recommended for a fresh build).
2. Switch to the **🤖 Autonomous Agent** tab in the Web UI.
3. Upload a **reference image** — a real park photo, satellite view, or concept art showing what to build.
4. Choose your **Gemini model** (`gemini-2.5-flash` is fast; `gemini-2.5-pro` for complex building replication).
5. Set **Max iterations** (safety cap on how many Gemini queries to make).
6. Leave **Dry run ON** the first time to read the decision log without the agent touching your game.
7. When you're satisfied, turn **Dry run OFF** and click **▶️ Start Autonomous Build**.
8. Switch back to the game window — the agent takes control.
9. Press **ESC** or **Q** at any time (in-game) or click **⏹ Stop** in the UI to halt.

---

## 🛠️ Pipeline Architecture

```
GUIDED MODE:
blueprints ──▶ [vision]      ──▶ layout (normalised JSON)
layout     ──▶ [scan]        ──▶ in-game buildable dimensions
layout+dims──▶ [planner]     ──▶ scaled build plan (in-game units)
plan       ──▶ [controller]  ──▶ Planet Coaster (PyDirectInput)

AUTONOMOUS MODE:
reference + live screen ──▶ [Gemini vision] ──▶ JSON decision
JSON decision           ──▶ [autonomous.py] ──▶ PyDirectInput actions
                                            ──▶ spatial memory update
                                            ──▶ next sector navigation
```

---

## 📁 Repo Layout

```
├── pinokio.json / pinokio.js           # Pinokio manifest + menu
├── install.js / start.js / update.js / reset.js / link.js
├── app.py                              # Gradio UI + pipeline orchestration
├── requirements.txt
└── agent/
    ├── model.py            # Claude / Gemini / OpenAI client (text + vision, JSON)
    ├── vision.py           # blueprints → normalised layout JSON
    ├── dimensions.py       # scan buildable area (manual or vision)
    ├── planner.py          # scale-to-fit + build plan; camera nav in prompt
    ├── controller.py       # execute plan via PyDirectInput (dry-run by default)
    ├── memory.py           # run state + logging
    ├── schema.py           # layout / action schemas + validators
    ├── controls.py         # keybind defaults + game folder scanner
    ├── tools.py            # geometry, validation, and sandbox tools
    ├── ui_map.py           # ★ Planet Coaster 2 UI pixel coordinate map
    ├── spatial_memory.py   # ★ 8×8 park grid — tracks built vs. empty sectors
    └── autonomous.py       # ★ Gemini vision → decision → hardware input loop
```

> ★ = new in the autonomous agent update

---

## ⌨️ Keybindings (Planet Coaster 2 defaults)

| Action | Key |
|---|---|
| Terrain menu | `T` |
| Paths menu | `P` |
| Scenery / Build menu | `B` |
| Coasters menu | `R` |
| Rides menu | `Y` |
| Rotate object | `Z` |
| Adjust height | `Shift` |
| Cancel / deselect | `Escape` |
| Camera pan | `W A S D` |
| Zoom in / out | `Page Up` / `Page Down` |
| Camera orbit | Middle mouse drag |

Keybindings can be customised in the **Controls & Scanner** tab.

---

## 📦 Requirements

- **Windows** — Planet Coaster is a Windows game; `pydirectinput` is Windows-only.
- **Python 3.10+** — Pinokio manages the venv automatically.
- **Planet Coaster 1 or 2** installed and running at 1920×1080 (other resolutions work but UI coordinate scaling may need tuning in `agent/ui_map.py`).
- **API key** for at least one of:
  - Google Gemini (required for Autonomous Agent mode)
  - Anthropic Claude
  - OpenAI or compatible endpoint

### Python packages (auto-installed)
```
gradio           requests         pillow           mss
pyautogui        pydirectinput    numpy            opencv-python
keyboard         anthropic        google-genai     openai
```

---

## 🔒 Safety

- **Dry run mode** — all actions are logged but no mouse/keyboard input is sent. Always test here first.
- **PyDirectInput FAILSAFE** — enabled by default; moving the mouse to a screen corner aborts input.
- **ESC / Q kill-switch** — the autonomous agent monitors these keys on a background thread and releases all held keys/buttons before halting.
- **Iteration cap** — set *Max iterations* in the UI to limit how long the autonomous agent runs unattended.
- **Spatial memory** — the agent tracks completed sectors so it cannot get stuck in a build loop.

---

## 🤝 Getting API Keys

| Provider | Link |
|---|---|
| Google Gemini | https://aistudio.google.com/apikey |
| Anthropic Claude | https://console.anthropic.com/ |
| OpenAI | https://platform.openai.com/api-keys |

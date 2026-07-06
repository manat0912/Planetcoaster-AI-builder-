"""PlanetCoaster AI Builder agent package.

Modules:
    model           - closed-source LLM client (Claude / Gemini / OpenAI-compatible) with vision.
    vision          - blueprint / map / schematic -> structured layout JSON.
    dimensions      - scan the in-game buildable area (vision or manual calibration).
    planner         - layout + in-game dimensions -> scaled, validated build plan.
    controller      - execute a build plan in Planet Coaster via PyDirectInput/PyAutoGUI.
    memory          - lightweight run state / logging.
    schema          - JSON schemas + validators for layout and action plans.
    ui_map          - Planet Coaster 2 UI pixel coordinate map (1920×1080 baseline).
    spatial_memory  - 2-D grid tracking which park sectors have been built.
    autonomous      - Fully autonomous Gemini vision → decision → action loop.
"""

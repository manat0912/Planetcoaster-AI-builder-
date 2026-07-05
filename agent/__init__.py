"""PlanetCoaster AI Builder agent package.

Modules:
    model       - closed-source LLM client (Claude / Gemini / OpenAI-compatible) with vision.
    vision      - blueprint / map / schematic -> structured layout JSON.
    dimensions  - scan the in-game buildable area (vision or manual calibration).
    planner     - layout + in-game dimensions -> scaled, validated build plan.
    controller  - execute a build plan in Planet Coaster via PyAutoGUI.
    memory      - lightweight run state / logging.
    schema      - JSON schemas + validators for layout and action plans.
"""

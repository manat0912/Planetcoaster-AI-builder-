"""Lightweight run state and logging for the agent.

Keeps the extracted layout, scanned dimensions, generated plan and a running log
of executed actions so a build can be inspected, resumed or re-exported.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


class AgentMemory:
    def __init__(self) -> None:
        self.layout: dict[str, Any] | None = None
        self.ingame_dims: dict[str, Any] | None = None
        self.plan: list[dict[str, Any]] | None = None
        self.actions: list[dict[str, Any]] = []
        self.lines: list[str] = []

    # ── state ────────────────────────────────────────────────────────────────
    def save_layout(self, layout: dict[str, Any]) -> None:
        self.layout = layout

    def save_dims(self, dims: dict[str, Any]) -> None:
        self.ingame_dims = dims

    def save_plan(self, plan: list[dict[str, Any]]) -> None:
        self.plan = plan

    def log_action(self, action: dict[str, Any]) -> None:
        self.actions.append(action)

    # ── logging ────────────────────────────────────────────────────────────--
    def log(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        self.lines.append(line)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "agent.log", "a") as fh:
            fh.write(line + "\n")

    def text_log(self) -> str:
        return "\n".join(self.lines[-400:])

    # ── persistence ───────────────────────────────────────────────────────---
    def dump(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "layout": self.layout,
            "ingame_dims": self.ingame_dims,
            "plan": self.plan,
        }, indent=2))

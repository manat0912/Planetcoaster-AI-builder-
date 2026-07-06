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
        self.state_file = LOG_DIR.parent / "cache" / "last_build_state.json"

    # ── state ────────────────────────────────────────────────────────────────
    def save_layout(self, layout: dict[str, Any]) -> None:
        self.layout = layout

    def save_dims(self, dims: dict[str, Any]) -> None:
        self.ingame_dims = dims

    def save_plan(self, plan: list[dict[str, Any]]) -> None:
        self.plan = plan

    def save_state(self, index: int) -> None:
        """Save progress state to cache folder."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "layout": self.layout,
            "ingame_dims": self.ingame_dims,
            "plan": self.plan,
            "current_index": index,
            "timestamp": time.time()
        }, indent=2))

    def load_state(self) -> dict[str, Any] | None:
        """Load progress state from cache folder."""
        if not self.state_file.exists():
            return None
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return None

    def clear_state(self) -> None:
        """Remove progress state file."""
        if self.state_file.exists():
            try:
                self.state_file.unlink()
            except Exception:
                pass

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

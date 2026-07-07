"""Spatial memory: tracks which grid sectors of the park have been built.

The 2-D grid is overlaid on the game sandbox (default 1000×1000 m).
Each cell tracks build status, timestamp, and what was placed there.
Gemini receives this as a compact JSON string so it avoids re-building
finished areas and can navigate logically to the next empty sector.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


MEMORY_FILE = Path(__file__).resolve().parent.parent / "logs" / "spatial_memory.json"


@dataclass
class SectorInfo:
    status: str = "empty"       # empty | in_progress | complete
    timestamp: float = 0.0
    notes: str = ""
    build_count: int = 0


class ParkSpatialMemory:
    """10×10 (default) grid overlaid on the game sandbox.

    Coordinates
    -----------
    The grid divides [0..1]×[0..1] normalised space.  Each cell (r, c) covers
    the rectangle  [c/cols .. (c+1)/cols]×[r/rows .. (r+1)/rows].

    Usage
    -----
    >>> mem = ParkSpatialMemory()
    >>> mem.current_sector          # (0, 0) top-left
    >>> mem.get_next_empty_sector() # scan row-major for next empty cell
    >>> mem.register_complete(0, 0)
    >>> mem.to_gemini_string()      # compact string for the LLM prompt
    """

    def __init__(self, rows: int = 8, cols: int = 8):
        self.rows = rows
        self.cols = cols
        self._grid: list[list[SectorInfo]] = [
            [SectorInfo() for _ in range(cols)] for _ in range(rows)
        ]
        self.current_sector: Tuple[int, int] = (0, 0)
        self._load()
        if not MEMORY_FILE.exists():
            self.save()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if MEMORY_FILE.exists():
            try:
                data = json.loads(MEMORY_FILE.read_text())
                for r in range(min(self.rows, len(data))):
                    for c in range(min(self.cols, len(data[r]))):
                        cell = data[r][c]
                        self._grid[r][c] = SectorInfo(**cell)
            except Exception:
                pass  # start fresh if file is corrupt

    def save(self) -> None:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [
            [vars(self._grid[r][c]) for c in range(self.cols)]
            for r in range(self.rows)
        ]
        MEMORY_FILE.write_text(json.dumps(data, indent=2))

    def reset(self) -> None:
        self._grid = [[SectorInfo() for _ in range(self.cols)] for _ in range(self.rows)]
        self.current_sector = (0, 0)
        self.save()

    # ── public API ───────────────────────────────────────────────────────────

    def mark_in_progress(self, r: int, c: int) -> None:
        self._grid[r][c].status = "in_progress"
        self._grid[r][c].timestamp = time.time()
        self.save()

    def register_complete(self, r: int, c: int, notes: str = "") -> None:
        cell = self._grid[r][c]
        cell.status = "complete"
        cell.timestamp = time.time()
        cell.build_count += 1
        if notes:
            cell.notes = notes
        print(f"[MEMORY] Sector ({r},{c}) marked COMPLETE.")
        self.save()

    def get_next_empty_sector(self) -> Optional[Tuple[int, int]]:
        """Row-major scan for the next cell that is not complete."""
        for r in range(self.rows):
            for c in range(self.cols):
                if self._grid[r][c].status != "complete":
                    return (r, c)
        return None

    def sector_normalised_center(self, r: int, c: int) -> Tuple[float, float]:
        """Return the normalised (0-1) centre of a grid sector."""
        cx = (c + 0.5) / self.cols
        cy = (r + 0.5) / self.rows
        return cx, cy

    def sector_for_normalised(self, nx: float, ny: float) -> Tuple[int, int]:
        """Return (row, col) for a normalised coordinate."""
        c = min(int(nx * self.cols), self.cols - 1)
        r = min(int(ny * self.rows), self.rows - 1)
        return r, c

    def to_gemini_string(self) -> str:
        """Compact ASCII map  E=empty I=in_progress C=complete."""
        SYM = {"empty": "E", "in_progress": "I", "complete": "C"}
        rows = []
        for r in range(self.rows):
            rows.append("".join(SYM.get(self._grid[r][c].status, "?") for c in range(self.cols)))
        cr, cc = self.current_sector
        return "\n".join(rows) + f"\n(cursor={cr},{cc})"

    def numpy_grid(self) -> "np.ndarray":
        VAL = {"empty": 0, "in_progress": 1, "complete": 2}
        arr = np.zeros((self.rows, self.cols), dtype=int)
        for r in range(self.rows):
            for c in range(self.cols):
                arr[r, c] = VAL.get(self._grid[r][c].status, 0)
        return arr

    def all_complete(self) -> bool:
        return all(
            self._grid[r][c].status == "complete"
            for r in range(self.rows)
            for c in range(self.cols)
        )

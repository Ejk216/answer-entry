"""Phase timing for the race: every report carries its own stopwatch."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


class Tracker:
    def __init__(self) -> None:
        self.phases: dict[str, float] = {}
        self._order: list[str] = []

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.phases[name] = self.phases.get(name, 0.0) + (time.perf_counter() - t0)
            if name not in self._order:
                self._order.append(name)

    def report(self) -> dict[str, object]:
        return {
            "total_s": round(sum(self.phases.values()), 2),
            "phases": {k: round(self.phases[k], 2) for k in self._order},
        }

    def summary(self) -> str:
        parts = [f"{k}={self.phases[k]:.1f}s" for k in self._order]
        parts.append(f"total={sum(self.phases.values()):.1f}s")
        return "  ".join(parts)

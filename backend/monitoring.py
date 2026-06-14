"""
In-memory metrics and health tracking for the D2C automation engine.
Accessible via GET /health/detailed and GET /api/metrics.
"""
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Deque

@dataclass
class Metrics:
    _start_time: float = field(default_factory=time.time)
    _counters: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _timings: Dict[str, Deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=100)))
    _errors: Deque = field(default_factory=lambda: deque(maxlen=50))

    def inc(self, key: str, amount: int = 1):
        self._counters[key] += amount

    def timing(self, key: str, ms: float):
        self._timings[key].append(ms)

    def error(self, source: str, message: str):
        self._errors.append({"source": source, "message": str(message)[:200], "ts": time.time()})
        self.inc(f"errors.{source}")

    def summary(self) -> dict:
        uptime = time.time() - self._start_time
        avg_timings = {
            k: round(sum(v) / len(v), 2) if v else 0
            for k, v in self._timings.items()
        }
        return {
            "uptime_seconds": round(uptime),
            "counters": dict(self._counters),
            "avg_timings_ms": avg_timings,
            "recent_errors": list(self._errors)[-10:],
        }


metrics = Metrics()

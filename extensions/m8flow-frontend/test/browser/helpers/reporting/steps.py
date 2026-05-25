"""Step-based reporting for HTML/PDF (optional)."""

from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from typing import Iterator

from helpers.reporting import collector as _collector_mod

_step_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "report_step_depth", default=0
)


@contextmanager
def report_step(title: str) -> Iterator[None]:
    """Record a named step for the current test (requires QA reporting active).

    Steps appear in order in the HTML timeline and in PDF failure sections.
    """
    col = getattr(_collector_mod, "_ACTIVE_COLLECTOR", None)
    nid = getattr(col, "_active_nodeid", None) if col else None

    depth = _step_depth.get()
    label = ("  " * depth) + title
    t0 = time.perf_counter()
    err: BaseException | None = None
    token = _step_depth.set(depth + 1)
    try:
        yield
    except BaseException as exc:
        err = exc
        raise
    finally:
        _step_depth.reset(token)
        elapsed = time.perf_counter() - t0
        ok = err is None
        if col is not None and nid:
            bucket = col.steps_by_node.setdefault(nid, [])
            bucket.append(
                {
                    "title": label,
                    "duration_sec": round(elapsed, 3),
                    "ok": ok,
                    "error": str(err) if err else "",
                }
            )

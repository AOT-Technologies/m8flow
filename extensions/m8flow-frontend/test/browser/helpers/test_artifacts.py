"""Shared paths under ``test-results`` for screenshots and reports."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

try:
    from slugify import slugify as _slugify
except ImportError:  # pragma: no cover

    def _slugify(value: str) -> str:  # type: ignore[misc]
        return (
            value.replace("/", "-")
            .replace("::", "-")
            .replace(" ", "-")
            .lower()
        )


def sanitize_nodeid(nodeid: str) -> str:
    """Match ``pytest_runtest_makereport`` screenshot filename convention."""
    return nodeid.replace("::", "_").replace("/", "_")


def playwright_results_subfolder_name(nodeid: str) -> str:
    """Same folder basename as pytest-playwright ``output_path`` (slugified node id, truncated).

    pytest-playwright stores ``trace.zip``, ``video*.webm``, PW screenshots under
    ``<--output>/<this>/``.
    """

    slug = _slugify(nodeid)
    if len(slug) < 256:
        return slug
    digest = hashlib.sha256(nodeid.encode()).hexdigest()[:7]
    return f"{slug[:100]}-{digest}-{slug[-100:]}"


def failure_screenshot_png_path(results_dir: str, nodeid: str) -> str:
    """Path used by :func:`conftest.pytest_runtest_makereport` on failure."""
    return os.path.join(results_dir, f"{sanitize_nodeid(nodeid)}.png")


def find_screenshot_paths(results_dir: str | Path, nodeid: str) -> list[Path]:
    """Return PNGs for a test: our failure capture plus Playwright artifacts under ``results_dir``."""
    root = Path(results_dir)
    out: list[Path] = []
    primary = root / f"{sanitize_nodeid(nodeid)}.png"
    if primary.exists():
        out.append(primary.resolve())

    if not root.is_dir():
        return out

    func = nodeid.split("::")[-1]
    slug = sanitize_nodeid(nodeid)
    for p in sorted(root.rglob("*.png")):
        rp = p.resolve()
        if rp in out:
            continue
        name = p.name
        rel = str(p.relative_to(root))
        if func in name or slug in rel or slug in name:
            out.append(rp)
            if len(out) >= 6:
                break
    return out[:6]


def find_playwright_artifacts(results_dir: Path, nodeid: str) -> dict[str, Path]:
    """Trace zip and video WebM copied by pytest-playwright into ``output_dir/<slug>/``."""
    sub = results_dir / playwright_results_subfolder_name(nodeid)
    if not sub.is_dir():
        return {}
    found: dict[str, Path] = {}
    for p in sorted(sub.glob("trace*.zip")):
        found.setdefault("trace", p.resolve())
        break
    for p in sorted(sub.glob("video*.webm")):
        found.setdefault("video", p.resolve())
        break
    return found


def file_link_uri(path: Path) -> str:
    """URI suitable for PDF link annotations (``file:///...``)."""
    return path.resolve().as_uri()

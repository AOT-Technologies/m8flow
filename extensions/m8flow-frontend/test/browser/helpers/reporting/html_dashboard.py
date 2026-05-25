"""Interactive HTML QA dashboard (template + JSON payload)."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from typing import Any
from urllib.parse import quote


def _category_from_module(module_fs: str) -> str:
    sep = "/" if "/" in module_fs else "\\"
    parts = [p for p in module_fs.split(sep) if p]
    if not parts:
        return "misc"
    if parts[0] == "browser" and len(parts) > 1:
        return parts[1]
    return parts[0]


def _display_short_name(nodeid: str, max_chars: int = 82) -> str:
    parts = nodeid.split("::")
    if len(parts) < 2:
        return nodeid
    stem = Path(parts[0].replace("\\", "/")).stem
    tail = parts[-1]
    lab = tail.split("[", 1)[0] if "[" in tail else tail
    s = stem + " \u203a " + lab
    if len(s) <= max_chars:
        return s
    return textwrap.shorten(s, width=max_chars, placeholder="\u2026")


def _rel_url(result_path: Path, report_dir: Path) -> str:
    try:
        rel = os.path.relpath(result_path.resolve(), report_dir.resolve())
        return quote(Path(rel).as_posix(), safe="/._-~")
    except ValueError:
        return ""


def _enrich_row(row: dict[str, Any], results_dir: Path, report_dir: Path) -> dict[str, Any]:
    from helpers.test_artifacts import (
        file_link_uri,
        find_playwright_artifacts,
        find_screenshot_paths,
    )

    nodeid = row["nodeid"]
    module_fs = nodeid.split("::")[0]
    module = module_fs.replace("\\", "/")
    test_name = nodeid.split("::")[-1]
    category = _category_from_module(module_fs)

    outcome = row["outcome"]
    shots = (
        find_screenshot_paths(results_dir, nodeid)
        if outcome in ("failed", "error")
        else []
    )
    shot_urls: list[str] = []
    for p in shots[:6]:
        u = _rel_url(p, report_dir)
        if u:
            shot_urls.append(u)

    arts = find_playwright_artifacts(results_dir, nodeid)
    art_links: dict[str, str] = {}
    for k, p in arts.items():
        try:
            art_links[k] = file_link_uri(p)
        except Exception:
            art_links[k] = str(p)

    return {
        **row,
        "module": module,
        "category": category,
        "test_name": test_name,
        "display_name": _display_short_name(nodeid),
        "screenshot_urls": shot_urls,
        "artifact_uris": art_links,
    }


def write_html_report(
    *,
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
    results_dir: Path,
) -> Path:
    report_dir = results_dir / "qa-report"
    report_dir.mkdir(parents=True, exist_ok=True)

    tpl_path = Path(__file__).resolve().parent / "dashboard.html"
    template = tpl_path.read_text(encoding="utf-8")

    tests = [_enrich_row(dict(r), results_dir, report_dir) for r in rows]
    payload = {"meta": meta, "tests": tests}
    raw_json = json.dumps(payload, ensure_ascii=False)
    safe_json = raw_json.replace("<", "\\u003c")

    html = template.replace("__SUITE_JSON__", safe_json)
    out_path = report_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path

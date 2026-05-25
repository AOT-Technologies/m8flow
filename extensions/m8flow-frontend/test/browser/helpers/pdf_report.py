"""Build a rich PDF summary of a pytest + Playwright session."""

from __future__ import annotations

import io
import os
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from helpers.test_artifacts import (
    file_link_uri,
    find_playwright_artifacts,
    find_screenshot_paths,
)


def _ascii_safe(text: str, limit: int = 32_000) -> str:
    """Latin-1-safe text when only core PDF fonts are available."""
    return text[:limit].encode("ascii", errors="backslashreplace").decode("ascii")


@dataclass
class PdfReportRecord:
    nodeid: str
    module: str
    category: str
    test_name: str
    outcome: str
    duration_sec: float
    started_iso: str
    finished_iso: str
    longrepr_text: str
    logs: list[str]
    failure_screenshots: list[Path]
    artifacts: dict[str, Path]


def _category_from_nodeid_fs(module_fs: str) -> str:
    sep = "/" if "/" in module_fs else "\\"
    parts = [p for p in module_fs.split(sep) if p]
    if not parts:
        return "misc"
    if parts[0] == "browser" and len(parts) > 1:
        return parts[1]
    return parts[0]


def build_pdf_records(
    session_reports: list[dict[str, Any]],
    results_dir: Path,
) -> list[PdfReportRecord]:
    """Map collected pytest rows to report records with artifacts."""
    root = results_dir
    records: list[PdfReportRecord] = []
    for row in session_reports:
        nodeid = row["nodeid"]
        module = nodeid.split("::")[0]
        category = _category_from_nodeid_fs(module)
        test_name = nodeid.split("::")[-1]
        outcome = row["outcome"]
        shots = (
            find_screenshot_paths(root, nodeid)
            if outcome in ("failed", "error")
            else []
        )
        arts = find_playwright_artifacts(root, nodeid)
        records.append(
            PdfReportRecord(
                nodeid=nodeid,
                module=module,
                category=category,
                test_name=test_name,
                outcome=outcome,
                duration_sec=float(row["duration"]),
                started_iso=str(row.get("started_iso") or ""),
                finished_iso=str(row.get("finished_iso") or ""),
                longrepr_text=row.get("longrepr_text") or "",
                logs=list(row.get("logs") or []),
                failure_screenshots=shots,
                artifacts=arts,
            )
        )
    return records


def _resolve_unicode_fonts() -> tuple[Path | None, Path | None]:
    """Prefer DejaVu on Linux, Arial on Windows, Arial on macOS."""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates_regular = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path(windir) / "Fonts" / "arial.ttf",
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    candidates_bold = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path(windir) / "Fonts" / "arialbd.ttf",
        Path("/Library/Fonts/Arial Bold.ttf"),
    ]
    reg = next((p for p in candidates_regular if p.is_file()), None)
    bold = next((p for p in candidates_bold if p.is_file()), None)
    return reg, bold


def _register_report_fonts(pdf: Any) -> tuple[bool, Callable[..., None]]:
    """Register Unicode TTF; return (unicode_enabled, set_font_fn(style, size))."""
    regular, bold = _resolve_unicode_fonts()
    family = "ReportUnicode"

    if regular is not None:
        pdf.add_font(family, "", str(regular))
        if bold is not None:
            pdf.add_font(family, "B", str(bold))

        def set_font(style: str = "", size: float = 10) -> None:
            st = "B" if style == "B" else ""
            if st == "B" and bold is None:
                pdf.set_font(family, style="", size=size)
            else:
                pdf.set_font(family, style=st, size=size)

        return True, set_font

    def set_font(style: str = "", size: float = 10) -> None:
        pdf.set_font("Helvetica", style=style, size=size)

    return False, set_font


def _outcome_chart_png(counts: dict[str, int]) -> bytes | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    labels = ["Passed", "Failed", "Skipped", "Errors"]
    keys = ["passed", "failed", "skipped", "error"]
    values = [counts.get(k, 0) for k in keys]
    if sum(values) == 0:
        return None

    colors = ["#2e7d32", "#c62828", "#f9a825", "#6a1b9a"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.8, 3.4), facecolor="#fafafa")
    ax1.set_facecolor("#ffffff")
    ax2.set_facecolor("#ffffff")
    nz_labels = [lbl for lbl, v in zip(labels, values) if v]
    nz_vals = [v for v in values if v > 0]
    nz_colors = [c for c, v in zip(colors, values) if v > 0]

    bars = ax1.bar(labels, values, color=colors, edgecolor="#333333", linewidth=0.6)
    ax1.set_ylabel("Tests")
    ax1.set_title("Outcomes (count)", fontsize=11, fontweight="bold", color="#1a1a1a")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.35)
    for b, v in zip(bars, values):
        if v:
            ax1.text(
                b.get_x() + b.get_width() / 2,
                b.get_height(),
                str(v),
                ha="center",
                va="bottom",
                fontsize=9,
                color="#222",
            )

    if nz_vals:
        wedges, texts, autotexts = ax2.pie(
            nz_vals,
            labels=nz_labels,
            colors=nz_colors,
            autopct="%1.0f%%",
            wedgeprops={"linewidth": 0.6, "edgecolor": "#333333"},
            textprops={"fontsize": 9},
        )
        for t in autotexts:
            t.set_color("#111111")
            t.set_fontweight("bold")

    ax2.set_title("Distribution", fontsize=11, fontweight="bold", color="#1a1a1a")
    fig.suptitle("Execution summary", fontsize=12, fontweight="bold", color="#1a1a1a", y=1.02)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    return buf.getvalue()


def _module_duration_chart_png(records: list[PdfReportRecord]) -> bytes | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    totals: defaultdict[str, float] = defaultdict(float)
    for r in records:
        totals[r.module] += r.duration_sec
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:14]
    if not items:
        return None

    modules = [textwrap.shorten(k.replace("\\", "/"), width=42, placeholder="…") for k, _ in items]
    vals = [v for _, v in items]

    fig, ax = plt.subplots(figsize=(6.4, max(3.2, 0.35 * len(items))), facecolor="#fafafa")
    ax.set_facecolor("#ffffff")
    y = range(len(modules))
    ax.barh(list(y), vals, color="#1565c0", edgecolor="#0d47a1", linewidth=0.5)
    ax.set_yticks(list(y))
    ax.set_yticklabels(modules, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Total duration (seconds)")
    ax.set_title("Time by module", fontsize=12, fontweight="bold", color="#1a1a1a")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.grid(True, linestyle="--", alpha=0.35)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    return buf.getvalue()


def _badge_palette(outcome: str) -> tuple[int, int, int]:
    o = outcome.lower()
    if o == "passed":
        return (46, 125, 50)
    if o == "failed":
        return (198, 40, 40)
    if o == "skipped":
        return (245, 124, 0)
    return (106, 27, 154)


def write_session_pdf(
    *,
    records: list[PdfReportRecord],
    output_path: Path,
    meta: dict[str, Any],
) -> None:
    """Render records into a PDF (fpdf2 + optional matplotlib PNGs)."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos, Align, WrapMode

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(14, 14, 14)
    unicode_fonts, set_font_fn = _register_report_fonts(pdf)

    def set_font(style: str = "", size: float = 10) -> None:
        set_font_fn(style=style, size=size)

    def mcell(text: str, h: float, size: float = 9, bold: bool = False) -> None:
        body = text if unicode_fonts else _ascii_safe(text)
        set_font(style="B" if bold else "", size=size)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            pdf.epw,
            h,
            body,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
            wrapmode=WrapMode.CHAR,
        )

    def ink_link(text: str, uri: str, h: float = 6) -> None:
        """Clickable URI (``file://`` support depends on PDF viewer)."""
        display = text if unicode_fonts else _ascii_safe(text)
        set_font(size=9)
        pdf.set_text_color(0, 102, 204)
        w = min(pdf.epw, pdf.get_string_width(display) + 3)
        pdf.cell(
            w,
            h,
            display,
            border=0,
            align=Align.L,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
            link=uri,
        )
        pdf.set_text_color(0, 0, 0)

    def badge_pill(label: str, outcome: str, x: float | None = None) -> None:
        r, g, b = _badge_palette(outcome)
        if x is not None:
            pdf.set_x(x)
        pdf.set_fill_color(r, g, b)
        pdf.set_text_color(255, 255, 255)
        set_font(style="B", size=9)
        w = pdf.get_string_width(label) + 8
        pdf.cell(min(w, pdf.w - pdf.r_margin - pdf.get_x()), 7, label, align=Align.C, fill=True)
        pdf.set_text_color(0, 0, 0)

    counts = meta.get("counts", {})
    env = meta.get("environment") or {}

    pdf.add_page()
    # Banner
    pdf.set_fill_color(240, 244, 248)
    pdf.rect(0, 0, 210, 28, style="F")
    set_font(style="B", size=18)
    pdf.set_xy(pdf.l_margin, 10)
    pdf.cell(0, 10, "Playwright · Pytest execution report")

    pdf.set_xy(pdf.l_margin, 32)
    set_font(size=10)
    finish = meta.get("session_finished_iso", "")
    start = meta.get("session_started_iso", "")
    mcell(f"Generated (UTC): {finish}\nSession window: {start} → {finish}", h=5.5)

    # Environment block
    set_font(style="B", size=11)
    pdf.set_x(pdf.l_margin)
    pdf.cell(
        pdf.epw,
        8,
        "Environment",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    set_font(size=9)
    lines = [
        f"Platform: {env.get('platform', '')}",
        f"Python: {env.get('python', '')}",
        f"Pytest: {env.get('pytest', '')}",
        f"Playwright: {env.get('playwright', '')}",
        f"Browsers CLI: {env.get('browsers_cli', '')}",
        f"E2E URL: {env.get('e2e_url', '')}",
        (
            "Capture: "
            f"tracing={env.get('tracing_opt', '')}, "
            f"video={env.get('video_opt', '')}, "
            f"screenshot={env.get('screenshot_opt', '')}"
        ),
        f"Results directory: {env.get('results_dir', '')}",
    ]
    mcell("\n".join(lines), h=5)

    # Summary badges row
    pdf.ln(2)
    set_font(style="B", size=11)
    pdf.set_x(pdf.l_margin)
    pdf.cell(pdf.epw, 8, "Outcome totals", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_x(pdf.l_margin)
    xb = pdf.l_margin
    for label, key, outcome_hint in (
        ("Passed", "passed", "passed"),
        ("Failed", "failed", "failed"),
        ("Skipped", "skipped", "skipped"),
        ("Errors", "error", "error"),
    ):
        txt = f" {label}: {counts.get(key, 0)} "
        badge_pill(txt.strip(), outcome_hint, x=xb)
        xb = pdf.get_x() + 4

    # Charts
    bar_png = _outcome_chart_png(counts)
    if bar_png:
        pdf.image(io.BytesIO(bar_png), x=pdf.l_margin, w=min(pdf.epw, 176))
        pdf.ln(2)
    mod_png = _module_duration_chart_png(records)
    if mod_png:
        pdf.image(io.BytesIO(mod_png), x=pdf.l_margin, w=min(pdf.epw, 176), keep_aspect_ratio=True)
        pdf.ln(4)

    # Group by category then module
    by_cat: defaultdict[str, list[PdfReportRecord]] = defaultdict(list)
    for r in records:
        by_cat[r.category].append(r)
    cats = sorted(by_cat.keys(), key=lambda c: (-len(by_cat[c]), c))

    for cat in cats:
        pdf.add_page()
        set_font(style="B", size=14)
        pdf.set_x(pdf.l_margin)
        pdf.cell(
            pdf.epw,
            10,
            f"Category: {cat}",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        by_mod: defaultdict[str, list[PdfReportRecord]] = defaultdict(list)
        for r in by_cat[cat]:
            by_mod[r.module].append(r)
        mods = sorted(by_mod.keys())

        set_font(style="B", size=10)
        mcell(f"Modules in this category: {len(mods)}", h=6, bold=True)
        pdf.ln(1)

        for mod in mods:
            mod_recs = by_mod[mod]
            sub = defaultdict(int)
            for r in mod_recs:
                sub[r.outcome] += 1
            set_font(style="B", size=11)
            mcell(mod.replace("/", " / "), h=7, bold=True)
            set_font(size=9)
            mcell(
                f"Totals — passed: {sub.get('passed', 0)}, "
                f"failed: {sub.get('failed', 0)}, "
                f"skipped: {sub.get('skipped', 0)}, "
                f"errors: {sub.get('error', 0)}",
                h=5,
            )
            pdf.ln(2)

            for rec in sorted(mod_recs, key=lambda rr: rr.test_name):
                pdf.ln(2)
                pdf.set_draw_color(200, 206, 216)
                pdf.set_line_width(0.25)
                yy = pdf.get_y()
                pdf.line(pdf.l_margin, yy, pdf.w - pdf.r_margin, yy)
                pdf.ln(3)

                badge_pill(rec.outcome.upper(), rec.outcome, x=pdf.l_margin)
                pdf.ln(9)
                set_font(style="B", size=11)
                mcell(rec.test_name, h=6.5, bold=True, size=11)
                timing = (
                    f"Duration: {rec.duration_sec:.2f}s"
                    + (f"  ·  Started (UTC): {rec.started_iso}" if rec.started_iso else "")
                    + (f"  ·  Finished (UTC): {rec.finished_iso}" if rec.finished_iso else "")
                )
                set_font(size=9)
                mcell(timing, h=5)
                mcell(f"Module: {rec.module}", h=5)
                mcell(f"Node ID: {rec.nodeid}", h=5)

                if rec.artifacts:
                    pdf.ln(1)
                    set_font(style="B", size=9)
                    pdf.cell(
                        0,
                        6,
                        "Playwright artifacts (click opens file URI if supported)",
                        new_x=XPos.LMARGIN,
                        new_y=YPos.NEXT,
                    )
                    for label, pth in sorted(rec.artifacts.items()):
                        uri = file_link_uri(pth)
                        ink_link(f"Open {label}: {pth.name}", uri)

                pdf.ln(1)
                set_font(style="B", size=9)
                n_log = len(rec.logs)
                pdf.cell(
                    0,
                    6,
                    f"Logging ({n_log} lines, stdlib · setup + call)",
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )
                set_font(size=7.5)
                mcell(
                    "Mirrors pytest log_cli_format and log_cli_level when attaching the PDF capture handler.",
                    h=4,
                    size=7.5,
                )
                if rec.logs:
                    set_font(size=8)
                    log_txt = "\n".join(rec.logs[-150:])
                    mcell(log_txt, h=4, size=8)
                else:
                    set_font(size=8)
                    mcell(
                        "(No lines captured — no records reached the root logger at "
                        "the configured level, or a logger disabled propagation.)",
                        h=4,
                        size=8,
                    )

                if rec.longrepr_text and rec.outcome in ("failed", "skipped"):
                    snippet = (
                        rec.longrepr_text
                        if len(rec.longrepr_text) <= 5000
                        else rec.longrepr_text[:4980] + "\n…"
                    )
                    pdf.ln(1)
                    set_font(style="B", size=9)
                    title = "Stack trace" if rec.outcome == "failed" else "Skip reason"
                    pdf.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    mcell(snippet, h=4.2, size=8)

                for idx, shot in enumerate(rec.failure_screenshots[:4]):
                    pdf.ln(2)
                    pdf.set_fill_color(250, 250, 252)
                    pdf.set_draw_color(220, 224, 230)
                    hh = pdf.get_y()
                    pdf.rect(pdf.l_margin, hh - 2, pdf.epw, 1, style="F")
                    set_font(style="B", size=11)
                    mcell(f"Failure screenshot [{idx + 1}]", h=7, bold=True)
                    set_font(size=8)
                    mcell(str(shot), h=5)
                    try:
                        pdf.set_x(pdf.l_margin)
                        pdf.image(str(shot), w=min(186, pdf.epw))
                    except Exception as exc:
                        set_font(size=9)
                        mcell(f"(Could not embed image: {exc})", h=5)

                pdf.ln(4)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))

"""Stakeholder-facing executive PDF summary (distinct from HTML diagnostics)."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from pathlib import PurePath
from typing import Any

from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from fpdf import FPDF
from fpdf.enums import Align, WrapMode, XPos, YPos

from helpers.pdf_report import _ascii_safe, _outcome_chart_png, _register_report_fonts
from helpers.test_artifacts import find_screenshot_paths


_COLORS_HEX = {
    "pass": "#1b7f4b",
    "fail": "#c41e3a",
    "skip": "#d97706",
    "error": "#5b2c91",
    "accent": "#0b5fff",
    "ink": "#1a1d23",
    "muted": "#5c6570",
}


def _category_from_nodeid_fs(module_fs: str) -> str:
    sep = "/" if "/" in module_fs else "\\"
    parts = [p for p in module_fs.split(sep) if p]
    if not parts:
        return "misc"
    if parts[0] == "browser" and len(parts) > 1:
        return parts[1]
    return parts[0]


def _compact_case_name(nodeid: str, max_chars: int = 58) -> str:
    raw = PurePath(nodeid.split("::")[0])
    fname = raw.stem
    tail = nodeid.split("::")[-1]
    lab = tail.split("[", 1)[0] if "[" in tail else tail
    s = f"{fname} › {lab}"
    if len(s) <= max_chars:
        return s
    return textwrap.shorten(s, width=max_chars, placeholder="…")


def _save_category_distribution_png(rows: list[dict[str, Any]], path: Path) -> None:
    cat_count: dict[str, int] = {}
    for r in rows:
        mod = str(r["nodeid"]).split("::")[0]
        c = _category_from_nodeid_fs(mod)
        cat_count[c] = cat_count.get(c, 0) + 1
    cats = sorted(cat_count.keys(), key=lambda k: (-cat_count[k], k))

    fig, ax = plt.subplots(figsize=(6.2, 3.85), facecolor="#fafbff")
    ax.set_facecolor("#ffffff")
    top = cats[:14]
    bar_c = [_COLORS_HEX["accent"]] * len(top)
    ax.barh(top, [cat_count[c] for c in top], color=bar_c, height=0.62, alpha=0.88)
    ax.invert_yaxis()
    ax.set_xlabel("Test count")
    ax.set_title(
        "Coverage by functional area",
        fontsize=11.5,
        fontweight="bold",
        color=_COLORS_HEX["ink"],
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.grid(True, linestyle=(0, (1, 3)), alpha=0.45)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _save_slowest_png(rows: list[dict[str, Any]], path: Path, *, top_n: int = 12) -> None:
    ranked = sorted(
        rows,
        key=lambda z: (-float(z.get("duration", 0)), str(z["nodeid"])),
    )[:top_n]
    if not ranked:
        fig, ax = plt.subplots(figsize=(6.0, 2.2), facecolor="#fafbff")
        ax.text(0.5, 0.5, "No tests", ha="center", va="center", fontsize=11)
        ax.axis("off")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return

    labs = [_compact_case_name(str(r["nodeid"]), max_chars=40) for r in ranked][::-1]
    vals = [float(r.get("duration", 0)) for r in ranked][::-1]
    cols = [
        _COLORS_HEX["fail"] if r.get("outcome") in ("failed", "error") else _COLORS_HEX["accent"]
        for r in ranked
    ][::-1]

    fig, ax = plt.subplots(
        figsize=(6.3, max(3.8, top_n * 0.38)),
        facecolor="#fafbff",
    )
    ax.set_facecolor("#ffffff")
    y = list(range(len(labs)))
    ax.barh(y, vals, height=0.55, color=cols, alpha=0.9, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labs, fontsize=8)
    ax.set_xlabel("Duration (seconds)")
    ax.set_title(
        "Slowest tests",
        fontsize=11.5,
        fontweight="bold",
        color=_COLORS_HEX["ink"],
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.grid(True, linestyle=(0, (1, 3)), alpha=0.45)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _save_timeline_png(rows: list[dict[str, Any]], path: Path) -> None:
    """Cumulative elapsed time through the suite (pytest run order)."""
    durs = [float(r.get("duration", 0)) for r in rows]
    if not durs:
        fig, ax = plt.subplots(figsize=(6.2, 2.9), facecolor="#fafbff")
        ax.text(0.5, 0.5, "No tests", ha="center", fontsize=11)
        ax.axis("off")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return

    cumulative: list[float] = []
    s = 0.0
    for d in durs:
        s += d
        cumulative.append(s)
    x_idx = list(range(1, len(durs) + 1))

    fig, ax = plt.subplots(figsize=(6.2, 2.95), facecolor="#fafbff")
    ax.set_facecolor("#ffffff")
    ax.fill_between(x_idx, 0, cumulative, alpha=0.18, color=_COLORS_HEX["accent"])
    ax.plot(x_idx, cumulative, color=_COLORS_HEX["accent"], linewidth=2)
    ax.scatter([len(x_idx)], [cumulative[-1]], color=_COLORS_HEX["accent"], s=42, zorder=4)
    ax.set_title(
        "Suite execution timeline (cumulative s)",
        fontsize=11.5,
        fontweight="bold",
        color=_COLORS_HEX["ink"],
    )
    ax.set_xlabel("Test index (#)")
    ax.set_ylabel("Cumulative duration (s)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, linestyle=(0, (1, 3)), alpha=0.45)
    ax.set_xlim(1, len(x_idx) + max(1, int(len(x_idx) * 0.02)))
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _save_kpi_dashboard_png(
    *,
    counts: dict[str, int],
    meta: dict[str, Any],
    rows: list[dict[str, Any]],
    total_duration: float,
    path: Path,
) -> None:
    passed, failed = counts.get("passed", 0), counts.get("failed", 0)
    skipped = counts.get("skipped", 0)
    errors = counts.get("error", 0)
    total_tests = meta.get("total_tests", len(rows))
    denom = passed + failed + skipped + errors
    rate = (100.0 * passed / denom) if denom else 0.0
    avg = total_duration / max(len(rows), 1)

    failures = [r for r in rows if r.get("outcome") in ("failed", "error")]
    slowest_lab = "(—)"
    slowest_sec = ""
    ranked = sorted(rows, key=lambda z: (-float(z.get("duration", 0)), str(z["nodeid"])))
    if ranked:
        r0 = ranked[0]
        slowest_lab = _compact_case_name(str(r0["nodeid"]), max_chars=42)
        slowest_sec = f"{float(r0.get('duration', 0)):0.1f}s"

    fig = plt.figure(figsize=(7.4, 3.05), facecolor="#f4f6f9")

    specs = (
        ("Total\nexecuted", str(total_tests), _COLORS_HEX["ink"]),
        ("Pass rate", f"{rate:0.0f}%", _COLORS_HEX["pass"]),
        ("Passed", str(passed), _COLORS_HEX["pass"]),
        ("Failed", str(failed), _COLORS_HEX["fail"]),
        ("Skipped", str(skipped), _COLORS_HEX["skip"]),
        (
            "Duration",
            (f"{total_duration / 60.0:.1f} min" if total_duration >= 60 else f"{total_duration:.1f}s"),
            _COLORS_HEX["accent"],
        ),
        ("Avg / test", f"{avg:.2f}s", _COLORS_HEX["muted"]),
        ("Open failures", str(len(failures)), _COLORS_HEX["fail"]),
    )

    ncol, nrow = 4, 2
    for idx, (label, val, clr) in enumerate(specs[:8]):
        ax = fig.add_subplot(nrow, ncol, idx + 1)
        ax.set_facecolor("#ffffff")
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.add_patch(
            plt.Rectangle(
                (0.04, 0.04),
                0.92,
                0.92,
                transform=ax.transAxes,
                fill=True,
                fc="#ffffff",
                ec="#e2e6ec",
                linewidth=1.2,
                zorder=0,
            )
        )
        ax.axhline(0.58, xmin=0.08, xmax=0.92, color=clr, linewidth=3)
        ax.text(0.5, 0.72, label, ha="center", va="bottom", fontsize=8.2, color=_COLORS_HEX["muted"])
        ax.text(0.5, 0.38, val, ha="center", va="top", fontsize=15, fontweight="bold", color=clr)

    plt.suptitle(
        "Execution dashboard · M8Flow KPI overview",
        fontsize=12.8,
        fontweight="bold",
        y=0.98,
        color=_COLORS_HEX["ink"],
    )
    fig.subplots_adjust(top=0.83, bottom=0.12, left=0.05, right=0.95, hspace=0.45, wspace=0.28)
    if slowest_sec:
        fig.text(
            0.5,
            0.02,
            "Slowest: " + slowest_lab + "  ·  " + slowest_sec,
            ha="center",
            fontsize=8.5,
            color=_COLORS_HEX["muted"],
        )
    plt.savefig(path, dpi=155, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def _save_module_duration_png(rows: list[dict[str, Any]], path: Path, *, top_n: int = 14) -> None:
    """Total duration per test module (file stem), horizontal bars."""
    tot: dict[str, float] = defaultdict(float)
    for r in rows:
        stem = PurePath(str(r["nodeid"]).split("::")[0]).stem
        tot[stem] += float(r.get("duration", 0))
    items = sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    if not items:
        fig, ax = plt.subplots(figsize=(6.0, 2.0), facecolor="#fafbff")
        ax.text(0.5, 0.5, "No data", ha="center")
        ax.axis("off")
        fig.savefig(path, dpi=115, bbox_inches="tight")
        plt.close(fig)
        return

    labels = [k[:36] for k, _ in items][::-1]
    vals = [v for _, v in items][::-1]
    fig, ax = plt.subplots(figsize=(6.6, max(3.5, top_n * 0.32)), facecolor="#fafbff")
    ax.set_facecolor("#ffffff")
    y = list(range(len(labels)))
    ax.barh(y, vals, height=0.52, color="#059669", alpha=0.85, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Seconds (sum)")
    ax.set_title(
        "Time by module (sum of case duration)",
        fontsize=11.2,
        fontweight="bold",
        color=_COLORS_HEX["ink"],
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.grid(True, linestyle=(0, (1, 3)), alpha=0.45)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _save_category_duration_png(rows: list[dict[str, Any]], path: Path, *, top_n: int = 12) -> None:
    """Duration share by functional area (horizontal)."""
    tot: dict[str, float] = defaultdict(float)
    for r in rows:
        ar = _category_from_nodeid_fs(str(r["nodeid"]).split("::")[0])
        tot[ar] += float(r.get("duration", 0))
    items = sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    if not items:
        fig, ax = plt.subplots(figsize=(5.5, 2.0), facecolor="#fafbff")
        ax.text(0.5, 0.5, "No data", ha="center")
        ax.axis("off")
        fig.savefig(path, dpi=115, bbox_inches="tight")
        plt.close(fig)
        return

    labels = [k[:22] for k, _ in items][::-1]
    vals = [v for _, v in items][::-1]
    fig, ax = plt.subplots(figsize=(6.2, max(3.4, len(items) * 0.36)), facecolor="#fafbff")
    ax.set_facecolor("#ffffff")
    y = list(range(len(labels)))
    ax.barh(y, vals, height=0.55, color=_COLORS_HEX["accent"], alpha=0.88, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_xlabel("Seconds (sum)")
    ax.set_title(
        "Time by functional area",
        fontsize=11.2,
        fontweight="bold",
        color=_COLORS_HEX["ink"],
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.grid(True, linestyle=(0, (1, 3)), alpha=0.45)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _recommendation_bullets(
    rows: list[dict[str, Any]],
    counts: dict[str, int],
    total_duration: float,
    env: dict[str, Any],
) -> list[str]:
    n = sum(counts.get(k, 0) for k in ("passed", "failed", "skipped", "error"))
    pf, fl = counts.get("passed", 0), counts.get("failed", 0) + counts.get("error", 0)
    sk = counts.get("skipped", 0)
    out: list[str] = []
    if n and fl == 0 and pf == n:
        out.append("All executed tests passed — suitable baseline for release or merge queue.")
    elif fl > 0:
        out.append(
            f"Triage {fl} failing case(s) first; link Playwright traces and screenshots in your tracker."
        )
    if sk > 0 and n and sk / n >= 0.25:
        out.append("Elevated skip rate — verify seed data, tenant, and environment flags.")
    avg = total_duration / max(len(rows), 1)
    if avg > 30 and len(rows) > 3:
        out.append("Consider parallel CI shards or profiling the slowest module.")
    tr = str(env.get("tracing_opt", "")).lower().strip()
    if tr in ("off", "none"):
        out.append("For hard-to-reproduce failures, run with tracing enabled (e.g. retain-on-failure).")
    if not out:
        out.append(
            "Maintain suite hygiene: flake review, stable selectors, and periodic trace sampling."
        )
    return out[:5]


def _stack_snippet(longrepr_text: str, limit: int = 750) -> str:
    t = (longrepr_text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _save_outcome_pie_only_png(counts: dict[str, int], path: Path) -> None:
    """Compact pie for executive page (no bar)."""
    labels = ["Passed", "Failed", "Skipped", "Errors"]
    keys = ["passed", "failed", "skipped", "error"]
    values = [counts.get(k, 0) for k in keys]
    nz = [(l, v) for l, v in zip(labels, values) if v]
    if not nz:
        fig, ax = plt.subplots(figsize=(3.2, 3.2), facecolor="#fafbff")
        ax.text(0.5, 0.5, "No data", ha="center")
        ax.axis("off")
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return
    lbs, vals = zip(*nz)
    colors = []
    for l in lbs:
        if l == "Passed":
            colors.append(_COLORS_HEX["pass"])
        elif l == "Failed":
            colors.append(_COLORS_HEX["fail"])
        elif l == "Skipped":
            colors.append(_COLORS_HEX["skip"])
        else:
            colors.append(_COLORS_HEX["error"])
    fig, ax = plt.subplots(figsize=(3.4, 3.4), facecolor="#fafbff")
    ax.set_facecolor("#ffffff")
    ax.pie(
        vals,
        labels=lbs,
        colors=colors,
        autopct="%1.0f%%",
        textprops={"fontsize": 9},
        wedgeprops={"linewidth": 0.6, "edgecolor": "#dedede"},
    )
    ax.set_title("Outcome mix", fontsize=11, fontweight="bold", color=_COLORS_HEX["ink"])
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


class _ExecutivePDF(FPDF):
    """Branded header/footer (page 1 is full-bleed cover — no top bar)."""

    def __init__(self, subtitle: str) -> None:
        super().__init__(unit="mm", format="A4")
        self._brand_sub = subtitle
        self.alias_nb_pages()
        self.set_auto_page_break(auto=True, margin=18)

    def header(self) -> None:
        if self.page_no() <= 1:
            return
        self.set_fill_color(11, 101, 255)
        self.rect(0, 0, 210, 9.8, style="DF")
        wb = self.w - self.l_margin - self.r_margin
        self.set_xy(self.l_margin, 2.9)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8.8)
        self.cell(wb / 2, 5.0, txt="M8Flow · QA (Playwright)", align=Align.L)
        self.set_font("Helvetica", "", 7.35)
        self.cell(wb / 2, 5.0, txt=self._brand_sub[:62], align=Align.R)
        self.ln()
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", size=10)

    def footer(self) -> None:
        self.set_y(-10.8)
        yl = self.get_y()
        self.set_draw_color(226, 230, 236)
        self.line(self.l_margin, yl, self.w - self.r_margin, yl)
        self.ln(1.8)
        self.set_font("Helvetica", "I", 7.2)
        self.set_text_color(92, 101, 112)
        pw = self.w - self.l_margin - self.r_margin
        half = pw / 2
        self.cell(half, 4, txt="M8Flow · Playwright Test · Confidential", align=Align.L)
        self.set_font("Helvetica", "", 7.9)
        self.cell(
            half,
            4,
            txt="Page " + str(self.page_no()) + "/{nb}",
            align=Align.R,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )


def _status_badge_colors(outcome: str) -> tuple[int, int, int]:
    o = outcome.lower()
    if o == "passed":
        return (27, 127, 75)
    if o == "failed":
        return (196, 30, 58)
    if o == "skipped":
        return (217, 119, 6)
    return (91, 44, 145)


def write_executive_pdf(
    *,
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
    results_dir: Path,
    output_path: Path,
) -> Path:
    """Write a concise multi-page PDF: KPI canvas, charts, highlights, failures, compact table."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    counts = meta["counts"]
    env = meta.get("environment") or {}
    total_duration = sum(float(r.get("duration", 0)) for r in rows)

    fin = str(meta.get("session_finished_iso", ""))[:19].replace("T", " ")
    subtitle = fin + " · " + (env.get("e2e_url", "") or "M8Flow E2E")[:38]

    pdf = _ExecutivePDF(subtitle=subtitle)
    pdf.set_margins(14, 18, 14)
    unicode_fonts, set_font_base = _register_report_fonts(pdf)

    def set_font(style: str = "", size: float = 10) -> None:
        set_font_base(style=style, size=size)

    def mcell(text: str, h: float = 5, size: float = 10, bold: bool = False) -> None:
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

    def banner(title: str, *, sub: str = "") -> None:
        pdf.set_fill_color(11, 101, 255)
        pdf.set_text_color(255, 255, 255)
        set_font(style="B", size=12.5)
        t = title if unicode_fonts else _ascii_safe(title)
        pdf.cell(0, 10, txt=t, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        if sub:
            pdf.set_fill_color(245, 248, 255)
            pdf.set_text_color(40, 55, 85)
            set_font(size=9)
            pdf.cell(0, 6.5, txt=(sub if unicode_fonts else _ascii_safe(sub)), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    with tempfile.TemporaryDirectory(prefix="m8exe-") as tmp:
        tdir = Path(tmp)

        kpi_png = tdir / "kpi.png"
        _save_kpi_dashboard_png(
            counts=counts,
            meta=meta,
            rows=rows,
            total_duration=total_duration,
            path=kpi_png,
        )

        combo_png = tdir / "combo.png"
        png_bytes = _outcome_chart_png(counts)
        if png_bytes:
            combo_png.write_bytes(png_bytes)

        cat_png = tdir / "cats.png"
        _save_category_distribution_png(rows, cat_png)

        slow_png = tdir / "slow.png"
        _save_slowest_png(rows, slow_png)

        time_png = tdir / "time.png"
        _save_timeline_png(rows, time_png)

        pie_png = tdir / "pie.png"
        _save_outcome_pie_only_png(counts, pie_png)

        mod_png = tdir / "mod.png"
        _save_module_duration_png(rows, mod_png)

        cat_dur_png = tdir / "catdur.png"
        _save_category_duration_png(rows, cat_dur_png)

        rec_lines = _recommendation_bullets(rows, counts, total_duration, env)

        # —— Page 1: cover, KPI, highlights, recommendations (concise) ——
        pdf.add_page()
        pdf.set_fill_color(11, 101, 255)
        pdf.rect(0, 0, 210, 46, style="F")
        pdf.set_xy(14, 10)
        pdf.set_text_color(255, 255, 255)
        set_font(style="B", size=23)
        pdf.cell(0, 10, txt="M8Flow", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        set_font(size=10.5)
        pdf.cell(0, 5.5, txt="Quality automation · Playwright", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        set_font(size=9.8)
        pdf.set_text_color(230, 235, 255)
        pdf.cell(0, 5, txt="Executive summary for stakeholders", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.set_y(52)

        set_font(size=9.2)
        meta_line = [
            f"Session completed · {fin}",
            f"Playwright {env.get('playwright', 'n/a')} · Browsers {env.get('browsers_cli', 'chromium')}",
        ]
        if env.get("git_revision"):
            meta_line.append(f"Revision {env['git_revision']}")
        if env.get("ci_workflow"):
            meta_line.append(f"Pipeline {env['ci_workflow']}")
        for ln in meta_line:
            mcell(ln, h=4.8, size=9)

        pdf.ln(1)
        pdf.image(str(kpi_png), x=pdf.l_margin, w=pdf.epw)
        pdf.ln(2)

        banner("Execution highlights", sub="Key facts for this run.")
        denom = sum(counts.get(k, 0) for k in ("passed", "failed", "skipped", "error"))
        pass_rate = (100.0 * counts.get("passed", 0) / denom) if denom else 0.0
        failures_n = len([r for r in rows if r.get("outcome") in ("failed", "error")])
        slow = sorted(rows, key=lambda z: (-float(z.get("duration", 0)), str(z["nodeid"])))
        top_cat: dict[str, float] = {}
        for r in rows:
            ar = _category_from_nodeid_fs(str(r["nodeid"]).split("::")[0])
            top_cat[ar] = top_cat.get(ar, 0.0) + float(r.get("duration", 0))
        cat_peak = max(top_cat.items(), key=lambda kv: kv[1])[0] if top_cat else "—"

        bullets = [
            f"Pass rate {pass_rate:.1f}% across {denom} completed tests.",
            f"Total duration (sum of case times) {total_duration:.1f}s ({total_duration / 60.0:.1f} min).",
            f"Open defects (failed + error): {failures_n}.",
            f"Heaviest time by area: {cat_peak}.",
        ]
        if slow:
            bullets.append(
                "Slowest: "
                + _compact_case_name(str(slow[0]["nodeid"]), max_chars=70)
                + f" ({float(slow[0].get('duration', 0)):.1f}s)."
            )
        set_font(size=9.5)
        for b in bullets:
            line = "• " + b
            mcell(line if unicode_fonts else _ascii_safe(line), h=5.2, size=9.5)

        pdf.ln(1.5)
        banner("Recommendations", sub="Suggested follow-ups (automated heuristics).")
        set_font(size=9.2)
        for rec in rec_lines:
            mcell("• " + rec, h=5.0, size=9.2)

        # —— Page 2: analytics charts ——
        pdf.add_page()
        banner("Suite analytics", sub="Performance & distribution · M8Flow test suite (Playwright)")

        if png_bytes and combo_png.is_file():
            pdf.image(str(combo_png), x=pdf.l_margin, w=pdf.epw)
            pdf.ln(2)

        w_half = (pdf.epw - 4) / 2
        pdf.image(str(pie_png), x=pdf.l_margin, w=w_half)
        pdf.image(str(cat_png), x=pdf.l_margin + w_half + 4, w=w_half)
        pdf.ln(2)

        pdf.image(str(slow_png), x=pdf.l_margin, w=pdf.epw)
        pdf.ln(3)
        pdf.image(str(time_png), x=pdf.l_margin, w=pdf.epw)
        pdf.ln(3)
        pdf.image(str(mod_png), x=pdf.l_margin, w=pdf.epw)
        pdf.ln(3)
        pdf.image(str(cat_dur_png), x=pdf.l_margin, w=pdf.epw)

        # —— Failures (enlarged evidence blocks) ——
        failures = [r for r in rows if r.get("outcome") in ("failed", "error")]
        pdf.add_page()
        banner("Failure analysis", sub="Screenshots · excerpt · tail logs · M8Flow / Playwright")
        if not failures:
            mcell("No failed tests in this session.", size=11)
        else:
            for r in failures:
                nid = str(r["nodeid"])
                out = str(r.get("outcome", ""))

                if pdf.get_y() > 230:
                    pdf.add_page()

                y_block = pdf.get_y()
                pdf.set_fill_color(255, 247, 247)
                pdf.rect(pdf.l_margin, y_block, pdf.epw, 8.5, style="F")
                pdf.set_draw_color(196, 30, 58)
                pdf.line(pdf.l_margin, y_block, pdf.l_margin, y_block + 8.5)
                pdf.set_xy(pdf.l_margin + 3, y_block + 1.8)

                rgb = _status_badge_colors(out)
                pdf.set_fill_color(*rgb)
                pdf.set_text_color(255, 255, 255)
                set_font(style="B", size=8.5)
                badge = out.upper()[:8]
                title_w = pdf.epw - 32
                pdf.cell(26, 6.5, txt=badge, align=Align.C, fill=True)
                pdf.set_text_color(0, 0, 0)
                set_font(style="B", size=11)
                disp = _compact_case_name(nid, max_chars=92)
                pdf.cell(
                    title_w,
                    6.5,
                    txt=" " + (disp if unicode_fonts else _ascii_safe(disp)),
                    align=Align.L,
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                )
                pdf.set_x(pdf.l_margin + 2)

                err = str(r.get("error_summary") or "").strip()
                if err:
                    mcell(err, h=4.6, size=9.5)

                lr = str(r.get("longrepr_text") or "")
                if lr.strip():
                    set_font(style="B", size=9)
                    pdf.set_x(pdf.l_margin + 2)
                    pdf.cell(0, 5, txt="Detail (excerpt)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    set_font(size=7.4)
                    sn = _stack_snippet(lr, 950)
                    pdf.set_x(pdf.l_margin + 2)
                    mcell(sn if unicode_fonts else _ascii_safe(sn), h=3.35, size=7.4)

                steps = r.get("steps") or []
                if isinstance(steps, list) and steps:
                    set_font(style="B", size=9.2)
                    pdf.set_x(pdf.l_margin + 2)
                    pdf.cell(0, 5, txt="Steps", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    set_font(size=8.2)
                    for s in steps[:10]:
                        ti = str(s.get("title", ""))
                        ds = s.get("duration_sec", "")
                        st = f"  • {ti} ({ds}s)"
                        pdf.set_x(pdf.l_margin + 2)
                        mcell(st if unicode_fonts else _ascii_safe(st), h=4.0, size=8.0)

                logs_tail = "\n".join((r.get("logs") or [])[-14:])
                if logs_tail.strip():
                    mcell("Logs (tail)", bold=True, size=9.2)
                    pdf.set_x(pdf.l_margin + 2)
                    mcell(logs_tail, h=3.75, size=7.6)

                shots = find_screenshot_paths(results_dir, nid)[:6]
                shot_y = pdf.get_y() + 2
                if shots:
                    try:
                        if shot_y > 165:
                            pdf.add_page()
                            shot_y = pdf.get_y() + 2
                        avail_w = pdf.epw - 6
                        pdf.image(
                            str(shots[0].resolve()),
                            x=pdf.l_margin + 2,
                            y=shot_y,
                            w=avail_w,
                        )
                        pdf.set_y(shot_y + 88)

                        thumbs = shots[1:4]
                        if thumbs:
                            gap = 2.5
                            tw = (avail_w - gap * (len(thumbs) - 1)) / len(thumbs)
                            ty = pdf.get_y() + 2
                            for ti, sp in enumerate(thumbs):
                                pdf.image(
                                    str(sp.resolve()),
                                    x=pdf.l_margin + 2 + ti * (tw + gap),
                                    y=ty,
                                    w=tw,
                                )
                            pdf.set_y(ty + 42)
                    except (OSError, RuntimeError):
                        mcell("(Screenshot could not be embedded.)", size=8)
                else:
                    pdf.set_y(max(pdf.get_y(), shot_y))

                pdf.ln(5)

        # —— Passed overview (zebra) ——
        pdf.add_page()
        banner("Regression health · passed & skipped", sub="Readable names; zebra rows.")

        w_nm = pdf.epw * 0.54
        w_st = pdf.epw * 0.18
        w_du = pdf.epw * 0.13
        w_ar = pdf.epw - w_nm - w_st - w_du
        hh = 7.5
        pdf.set_fill_color(230, 236, 250)
        set_font(style="B", size=10)
        pdf.cell(w_nm, hh, txt="Test case", border=1, align=Align.L, fill=True)
        pdf.cell(w_st, hh, txt="Status", border=1, align=Align.C, fill=True)
        pdf.cell(w_du, hh, txt="Seconds", border=1, align=Align.R, fill=True)
        pdf.cell(w_ar, hh, txt="Area", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        good = sorted(
            (x for x in rows if x.get("outcome") in ("passed", "skipped")),
            key=lambda z: (-float(z.get("duration", 0)), str(z["nodeid"])),
        )
        if not good:
            mcell("(No passing or skipped tests recorded.)")
        else:
            set_font(size=8.9)
            for i, row in enumerate(good):
                nid_s = str(row["nodeid"])
                nm_disp = _compact_case_name(nid_s, max_chars=76)
                oc = str(row.get("outcome", ""))[:10]
                du = f"{float(row.get('duration', 0)):0.2f}"
                ar = _category_from_nodeid_fs(nid_s.split("::")[0])[:16]
                if pdf.get_y() > pdf.h - pdf.b_margin - 12:
                    pdf.add_page()
                    pdf.set_fill_color(230, 236, 250)
                    set_font(style="B", size=10)
                    pdf.cell(w_nm, hh, txt="Test case", border=1, align=Align.L, fill=True)
                    pdf.cell(w_st, hh, txt="Status", border=1, align=Align.C, fill=True)
                    pdf.cell(w_du, hh, txt="Seconds", border=1, align=Align.R, fill=True)
                    pdf.cell(w_ar, hh, txt="Area", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    set_font(size=8.9)

                fill = bool(i % 2)
                if fill:
                    pdf.set_fill_color(248, 249, 252)
                else:
                    pdf.set_fill_color(255, 255, 255)

                sto = oc.lower()
                set_font(size=9)
                pdf.cell(
                    w_nm,
                    hh,
                    txt=(nm_disp if unicode_fonts else _ascii_safe(nm_disp)),
                    border=1,
                    align=Align.L,
                    fill=True,
                )
                r_, g_, b_ = _status_badge_colors(sto)
                pdf.set_fill_color(r_, g_, b_)
                pdf.set_text_color(255, 255, 255)
                set_font(style="B", size=8.2)
                pdf.cell(w_st, hh, txt=oc.upper()[:7], border=1, align=Align.C, fill=True)
                pdf.set_fill_color(*(248, 249, 252) if fill else (255, 255, 255))
                pdf.set_text_color(0, 0, 0)
                set_font(style="", size=8.9)
                pdf.cell(w_du, hh, txt=du, border=1, align=Align.R, fill=True)
                pdf.cell(
                    w_ar,
                    hh,
                    txt=(ar if unicode_fonts else _ascii_safe(ar)),
                    border=1,
                    new_x=XPos.LMARGIN,
                    new_y=YPos.NEXT,
                    fill=True,
                )

        pdf.output(str(output_path))
        return output_path.resolve()


__all__ = ["write_executive_pdf"]

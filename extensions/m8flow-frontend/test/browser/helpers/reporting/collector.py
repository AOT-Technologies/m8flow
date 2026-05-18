"""Pytest session collector for M8Flow QA HTML + executive PDF reports."""

from __future__ import annotations

import importlib.metadata
import logging
import os
import platform
import re
import subprocess
import sys
import warnings
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from helpers.config import BASE_URL

# Set by :class:`QASessionCollector` during each test (for ``report_step``).
_ACTIVE_COLLECTOR: QASessionCollector | None = None


def _reporting_enabled(cfg: Any) -> bool:
    return bool(
        cfg.getoption("qa_report")
        or cfg.getoption("html_report")
        or cfg.getoption("pdf_report")
    )


def _git_short_sha(cwd: Path) -> str:
    for env_key in ("GITHUB_SHA", "CI_COMMIT_SHORT_SHA", "GIT_COMMIT"):
        v = os.environ.get(env_key, "").strip()
        if v:
            return v[:12]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
            timeout=3,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _browser_from_nodeid(nodeid: str) -> str:
    m = re.search(r"\[([^\]]+)\]\s*$", nodeid)
    return m.group(1) if m else "chromium"


def _error_head(longrepr: str, limit: int = 400) -> str:
    if not longrepr:
        return ""
    line = longrepr.strip().split("\n", 1)[0]
    return line[:limit]


class QAReportLogHandler(logging.Handler):
    def __init__(self, collector: QASessionCollector) -> None:
        super().__init__(level=logging.DEBUG)
        self.collector = collector
        self.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            nid = self.collector._active_nodeid
            if not nid:
                return
            self.collector.logs_by_node.setdefault(nid, []).append(self.format(record))
        except Exception:
            self.handleError(record)


class QASessionCollector:
    """Collects per-test data; writes HTML and/or executive PDF on session finish."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.logs_by_node: dict[str, list[str]] = {}
        self.steps_by_node: dict[str, list[dict[str, Any]]] = {}
        self.test_start_wall: dict[str, datetime] = {}
        self._active_nodeid: str | None = None
        self.session_started: datetime | None = None
        self.log_handler = QAReportLogHandler(self)
        self._log_handler_attached = False
        self._pytest_config = None

    def _configure_logging_from_ini(self, cfg: Any) -> None:
        log_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        try:
            lf = cfg.getini("log_cli_format")
            if lf and str(lf).strip():
                log_fmt = str(lf).strip()
        except ValueError:
            pass

        date_fmt = None
        try:
            dtf = cfg.getini("log_cli_date_format")
            if dtf and str(dtf).strip():
                date_fmt = str(dtf).strip()
        except ValueError:
            pass

        cap_level = logging.INFO
        try:
            lvl_raw = cfg.getini("log_cli_level")
            if lvl_raw:
                cap_level = getattr(
                    logging, str(lvl_raw).strip().upper(), logging.INFO
                )
        except ValueError:
            pass

        self.log_handler.setFormatter(logging.Formatter(log_fmt, datefmt=date_fmt))
        self.log_handler.setLevel(cap_level)

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        global _ACTIVE_COLLECTOR
        self._pytest_config = session.config
        if not _reporting_enabled(session.config):
            return

        self._configure_logging_from_ini(session.config)
        self.session_started = datetime.now(timezone.utc)
        root = logging.getLogger()
        if not self._log_handler_attached:
            root.addHandler(self.log_handler)
            self._log_handler_attached = True

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        global _ACTIVE_COLLECTOR
        if not _reporting_enabled(item.config):
            return
        nid = item.nodeid
        self._active_nodeid = nid
        _ACTIVE_COLLECTOR = self
        self.logs_by_node[nid] = []
        self.steps_by_node.pop(nid, None)
        self.test_start_wall[nid] = datetime.now(timezone.utc)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        global _ACTIVE_COLLECTOR
        if report.when != "call":
            return

        cfg = getattr(report, "session", None)
        cfg = getattr(cfg, "config", None) if cfg is not None else None
        if cfg is None:
            node = getattr(report, "node", None)
            cfg = getattr(node, "config", None)
        if cfg is None:
            cfg = self._pytest_config

        if cfg is None or not _reporting_enabled(cfg):
            return

        longrepr_text = ""
        if report.longrepr is not None and report.outcome in (
            "failed",
            "skipped",
            "error",
        ):
            longrepr_text = str(report.longrepr)

        start_wall = self.test_start_wall.pop(report.nodeid, None)
        dur = report.duration if report.duration is not None else 0.0
        finished = None
        if start_wall is not None:
            finished = start_wall + timedelta(seconds=float(dur))

        logs = list(self.logs_by_node.pop(report.nodeid, []))
        steps = list(self.steps_by_node.pop(report.nodeid, []))

        rerun_index = getattr(report, "rerun", None)

        browsers = cfg.getoption("browser") or []
        browser = _browser_from_nodeid(report.nodeid)
        if not browsers:
            browsers = ["chromium"]

        self.rows.append(
            {
                "nodeid": report.nodeid,
                "outcome": report.outcome,
                "duration": float(dur),
                "longrepr_text": longrepr_text,
                "error_summary": _error_head(longrepr_text),
                "logs": logs,
                "steps": steps,
                "started_iso": start_wall.isoformat() if start_wall else "",
                "finished_iso": finished.isoformat() if finished else "",
                "browser": browser,
                "rerun": rerun_index,
            }
        )
        self._active_nodeid = None
        _ACTIVE_COLLECTOR = None

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        global _ACTIVE_COLLECTOR
        _ACTIVE_COLLECTOR = None
        cfg = session.config

        if self._log_handler_attached:
            logging.getLogger().removeHandler(self.log_handler)
            self._log_handler_attached = False

        if not _reporting_enabled(cfg):
            return
        if cfg.getoption("collectonly"):
            return

        outcomes = Counter(r["outcome"] for r in self.rows)
        counts = {
            "passed": outcomes.get("passed", 0),
            "failed": outcomes.get("failed", 0),
            "skipped": outcomes.get("skipped", 0),
            "error": outcomes.get("error", 0),
        }

        pw_ver = "n/a"
        try:
            pw_ver = importlib.metadata.version("playwright")
        except Exception:
            pass

        browsers = cfg.getoption("browser") or []
        root_any = getattr(cfg, "rootpath", None)
        root_base = Path(str(root_any)) if root_any is not None else Path.cwd()
        results_dir = root_base / "test-results"

        cwd = Path(__file__).resolve().parents[2]
        env_pack = {
            "platform": platform.platform(),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "pytest": getattr(pytest, "__version__", "?"),
            "playwright": pw_ver,
            "browsers_cli": ", ".join(browsers) if browsers else "chromium (default)",
            "e2e_url": os.environ.get("E2E_URL", BASE_URL),
            "tracing_opt": str(cfg.getoption("tracing")),
            "video_opt": str(cfg.getoption("video")),
            "screenshot_opt": str(cfg.getoption("screenshot")),
            "results_dir": str(results_dir.resolve()),
            "git_revision": _git_short_sha(cwd),
            "ci_workflow": os.environ.get("GITHUB_WORKFLOW", "")
            or os.environ.get("CI_JOB_NAME", ""),
        }

        meta = {
            "counts": counts,
            "total_tests": len(self.rows),
            "session_started_iso": (
                self.session_started or datetime.now(timezone.utc)
            ).isoformat(),
            "session_finished_iso": datetime.now(timezone.utc).isoformat(),
            "environment": env_pack,
            "exit_status": exitstatus,
        }

        reporter = cfg.pluginmanager.get_plugin("terminalreporter")
        qa = cfg.getoption("qa_report")
        want_html = qa or cfg.getoption("html_report")
        want_pdf = qa or cfg.getoption("pdf_report")

        if want_html:
            try:
                from helpers.reporting import html_dashboard

                html_dashboard.write_html_report(
                    rows=self.rows,
                    meta=meta,
                    results_dir=results_dir.resolve(),
                )
                html_path = (results_dir / "qa-report" / "index.html").resolve()
                line = f"\nQA HTML report: {html_path}\n"
                if reporter:
                    reporter.write_line(line)
                else:
                    print(line, flush=True)
                print(f"QA HTML report: {html_path}", flush=True)
            except Exception as exc:
                print(f"M8Flow QA HTML report failed: {exc}", flush=True)
                warnings.warn(
                    f"M8Flow QA HTML report failed: {exc}",
                    stacklevel=1,
                )

        if want_pdf:
            try:
                from helpers.reporting import pdf_executive

                out = cfg.getoption("pdf_report_file")
                if out:
                    out_path = Path(out)
                else:
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    out_path = results_dir / f"m8flow-exec-summary-{ts}.pdf"

                pdf_executive.write_executive_pdf(
                    rows=self.rows,
                    meta=meta,
                    results_dir=results_dir.resolve(),
                    output_path=out_path,
                )
                line = f"\nExecutive PDF: {out_path.resolve()}\n"
                if reporter:
                    reporter.write_line(line)
                else:
                    print(line, flush=True)
            except Exception as exc:
                warnings.warn(
                    f"M8Flow executive PDF failed: {exc} "
                    '(install "fpdf2" and "matplotlib", e.g. uv sync --extra pdf).',
                    stacklevel=1,
                )

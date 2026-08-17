"""Guards the two invariants FILE_GATES depends on in check-upstream-copying.py:

1. Layer C1 markers (LGPL/GPL header text, upstream author handles) always fail,
   even for a file that has a FILE_GATES entry -- a gate ceilings a file's
   similarity/containment/block-size numbers, it must never suppress a marker hit.
2. A gated file never gets written back into a regenerated baseline. FILE_GATES and
   the baseline are two separate grandfathering mechanisms (a fixed ceiling vs. a
   tracked-and-driftable value); mixing them would let `--write-baseline` silently
   re-grandfather a gated file at a fresh, possibly worse, value.

Run with: pytest bin/tests/test_check_upstream_copying.py
(not wired into a CI job yet -- see .github/workflows/README.md for the gate's
actual `--diff`/`--all` invocations, which run the script as a CLI, not via pytest).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "check-upstream-copying.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_upstream_copying", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cuc():
    return _load_module()


@pytest.fixture()
def gated_path(cuc) -> str:
    """A real FILE_GATES key, so the test tracks the actual gate mechanism rather
    than a synthetic stand-in that could drift from how gates are actually keyed."""
    assert cuc.FILE_GATES, "FILE_GATES must not be empty for this test to be meaningful"
    return next(iter(cuc.FILE_GATES))


def test_marker_hit_fails_even_on_a_gated_file(cuc, gated_path):
    gate = cuc.FILE_GATES[gated_path]
    result = cuc.FileResult(
        apache_path=gated_path,
        upstream_path="some/upstream/counterpart.py",
        # Deliberately AT the gate's own ceiling (not over it), so only the marker
        # -- not ratio/containment/block drift -- should produce a violation.
        ratio=gate["ratio"],
        containment=gate["containment"],
        longest_block=gate["longest_block"],
        markers=["LGPL license header text"],
    )

    violations = cuc.evaluate(result, baseline={}, thr=cuc.DEFAULT_THRESHOLD,
                               ct=cuc.DEFAULT_CONTAINMENT, blk=cuc.DEFAULT_BLOCK_LINES)

    assert any("MARKER" in v and "never grandfathered" in v for v in violations), (
        f"a FILE_GATES entry ({gated_path}) must not suppress a Layer C1 marker hit, "
        f"got: {violations}"
    )


def test_gated_file_is_never_written_back_into_a_regenerated_baseline(cuc, gated_path):
    gate = cuc.FILE_GATES[gated_path]
    gated_result = cuc.FileResult(
        apache_path=gated_path,
        upstream_path="some/upstream/counterpart.py",
        # Comfortably over the gate's own ceiling, so build_baseline's _flagged()
        # check alone would include it if the FILE_GATES skip were missing/broken.
        ratio=min(1.0, gate["ratio"] + 0.1),
        containment=min(1.0, gate["containment"] + 0.1),
        longest_block=gate["longest_block"] + 10,
    )
    ungated_result = cuc.FileResult(
        apache_path="m8flow-backend/some/genuinely/new_copy.py",
        upstream_path="some/upstream/other.py",
        ratio=0.9,
        containment=0.9,
        longest_block=50,
    )

    baseline = cuc.build_baseline(
        [gated_result, ungated_result],
        thr=cuc.DEFAULT_THRESHOLD, ct=cuc.DEFAULT_CONTAINMENT, blk=cuc.DEFAULT_BLOCK_LINES,
    )

    assert gated_path not in baseline["files"], (
        f"a FILE_GATES entry ({gated_path}) must never be written back into the "
        "baseline -- its ceiling lives in FILE_GATES, not the baseline file"
    )
    assert ungated_result.apache_path in baseline["files"], (
        "sanity check: a genuinely new, non-gated flagged file must still be "
        "written into the baseline"
    )

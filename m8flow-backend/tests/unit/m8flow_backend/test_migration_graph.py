"""Regression coverage for the deployed Alembic merge topology."""

from __future__ import annotations

from pathlib import Path

from alembic.script import ScriptDirectory

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_HEAD = "b7e1c2d3f4a5"


def _required_revisions(script: ScriptDirectory, start: str) -> set[str]:
    """Return revisions an upgrade to the head must apply from ``start``."""
    current_ancestors = {
        revision.revision for revision in script.walk_revisions(base="base", head=start)
    }
    required: set[str] = set()
    pending = [_HEAD]
    while pending:
        revision_id = pending.pop()
        if revision_id in current_ancestors or revision_id in required:
            continue
        required.add(revision_id)
        node = script.get_revision(revision_id)
        parents = node.down_revision
        pending.extend(parents if isinstance(parents, tuple) else (parents,) if parents else ())
    return required


def test_deployed_merge_ancestry_is_preserved_and_cleanup_is_reachable():
    script = ScriptDirectory(str(_MIGRATIONS_DIR))

    assert script.get_heads() == [_HEAD]
    all_revisions = [
        revision.revision for revision in script.walk_revisions(base="base", head=_HEAD)
    ]
    assert len(all_revisions) == len(set(all_revisions))

    # These are the two heads that existed when the NATS and external-form
    # migrations were deployed. Both must reach the single current head.
    for start in ("a1b2c3d4e5f6", "7d4b1e9c3a20"):
        required = _required_revisions(script, start)
        assert _HEAD in required
        assert "f3243241c342" in required
        assert "d4e5f6a7b8c9" in required

    # A database already stamped at the original merge revision must still
    # receive the cleanup branch after the ancestry correction.
    from_old_merge = _required_revisions(script, "f3243241c342")
    assert "d4e5f6a7b8c9" in from_old_merge
    assert _HEAD in from_old_merge

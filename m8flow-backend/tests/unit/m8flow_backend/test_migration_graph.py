"""Regression coverage for the deployed Alembic merge topology."""

from __future__ import annotations

from pathlib import Path

from alembic.script import ScriptDirectory

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_UPSTREAM_MERGE = "c81d2e3f4a56"
# NATS event-history revoke; the run-stats index sits on top of it, then
# the error-row timestamp, then the signal registry.
_NATS_REVOKE = "c7e9a1b3d5f7"
_RUN_STATS_INDEX = "e9c4b2a71f53"
_ERROR_CREATED_AT = "d8e9f0a1b2c3"
_PREVIOUS_HEAD = "a3f4e5d6c7b8"
_HEAD = "b6c7d8e9f0a1"
_TERMINAL_REVISIONS = {_PREVIOUS_HEAD, _HEAD}


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
    assert "d1e2f3a4b5c6" in all_revisions
    assert _PREVIOUS_HEAD in all_revisions

    # These are the two heads that existed when the NATS and external-form
    # migrations were deployed. Both must reach the single current head.
    for start in ("a1b2c3d4e5f6", "7d4b1e9c3a20"):
        required = _required_revisions(script, start)
        assert _HEAD in required
        assert "f3243241c342" in required
        assert "d4e5f6a7b8c9" in required
        assert "c4d5e6f7a8b9" in required

    # A database already stamped at the original merge revision must still
    # receive the cleanup branch after the ancestry correction.
    from_old_merge = _required_revisions(script, "f3243241c342")
    assert "d4e5f6a7b8c9" in from_old_merge
    assert _HEAD in from_old_merge

    # Both feature branches must be reachable from the common host history.
    assert _required_revisions(script, "f7a8b9c0d1e2") == {
        "fa8b9c0d1e2f", "fbcad9e02138", "e2f3a4b5c6d7", "e1f2a3b4c5d6",
        "b603fd822b22", "9f2c6d4b8e71", _UPSTREAM_MERGE, _NATS_REVOKE, _RUN_STATS_INDEX, _ERROR_CREATED_AT,
        *_TERMINAL_REVISIONS,
    }
    assert _required_revisions(script, "fa8b9c0d1e2f") == {
        "d1e2f3a4b5c6",
        "d2f4a6b8c0e1",
        "e3f5a7c9d1b2",
        "f7a8b9c0d1e2",
        "fbcad9e02138",
        "e2f3a4b5c6d7",
        "e1f2a3b4c5d6",
        "b603fd822b22",
        "9f2c6d4b8e71",
        _UPSTREAM_MERGE,
        _NATS_REVOKE,
        _RUN_STATS_INDEX,
        _ERROR_CREATED_AT,
        *_TERMINAL_REVISIONS,
    }

    # Keep the upgrade paths for databases already stamped on either branch.
    assert _required_revisions(script, "fbcad9e02138") == {
        "e2f3a4b5c6d7", "e1f2a3b4c5d6", "b603fd822b22", "9f2c6d4b8e71", _UPSTREAM_MERGE, _NATS_REVOKE, _RUN_STATS_INDEX, _ERROR_CREATED_AT,
        *_TERMINAL_REVISIONS,
    }
    assert _required_revisions(script, "e2f3a4b5c6d7") == {
        "d2f4a6b8c0e1", "e3f5a7c9d1b2", "f7a8b9c0d1e2", "fa8b9c0d1e2f", "fbcad9e02138",
        "e1f2a3b4c5d6", "b603fd822b22", "9f2c6d4b8e71", _UPSTREAM_MERGE, _NATS_REVOKE, _RUN_STATS_INDEX,
        _ERROR_CREATED_AT, *_TERMINAL_REVISIONS,
    }
    assert _required_revisions(script, "b603fd822b22") == {
        "e2f3a4b5c6d7", "9f2c6d4b8e71", _UPSTREAM_MERGE, _NATS_REVOKE, _RUN_STATS_INDEX, _ERROR_CREATED_AT,
        *_TERMINAL_REVISIONS,
    }
    assert _required_revisions(script, "9f2c6d4b8e71") == {
        "e1f2a3b4c5d6", "b603fd822b22", _UPSTREAM_MERGE, _NATS_REVOKE, _RUN_STATS_INDEX, _ERROR_CREATED_AT,
        *_TERMINAL_REVISIONS,
    }

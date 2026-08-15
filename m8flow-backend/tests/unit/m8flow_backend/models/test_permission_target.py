from __future__ import annotations

import pytest

from spiffworkflow_backend.models.permission_target import PermissionTargetModel


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("process.start", "process.start"),
        ("  process.start  ", "process.start"),
        ("   ", None),
        ("", None),
        (None, None),
        (1, None),
    ],
)
def test_permission_target_init_normalizes_command(
    command: object, expected: str | None
) -> None:
    target = PermissionTargetModel(uri="/process-groups/%", command=command)  # type: ignore[arg-type]

    assert target.uri == "/process-groups/%"
    assert target.command == expected

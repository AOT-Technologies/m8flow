from __future__ import annotations
# ruff: noqa: E402

import sys
from pathlib import Path

import pytest

backend_root = Path(__file__).resolve().parents[4]
repo_root = backend_root.parent
demo_src = repo_root / "docker" / "vault" / "demo"

demo_src_str = str(demo_src)
if demo_src_str not in sys.path:
    sys.path.insert(0, demo_src_str)

from seeded_secrets import (
    DEMO_BOOTSTRAP_SECRET_NAME,
    DEMO_BOOTSTRAP_SECRET_VALUE,
    SeededSecretSpec,
    load_seeded_secret_specs,
)


def test_missing_secrets_file_falls_back_to_demo_bootstrap_secret(tmp_path: Path) -> None:
    messages: list[str] = []
    secrets_file = tmp_path / "secrets.yml"

    secrets = load_seeded_secret_specs(
        secrets_file,
        organization_alias="m8flow",
        organization_id="tenant-123",
        missing_file_message_factory=lambda path: f"missing {path}",
        logger=messages.append,
    )

    assert secrets == [
        SeededSecretSpec(
            tenant_reference="m8flow",
            tenant_id="tenant-123",
            secret_name=DEMO_BOOTSTRAP_SECRET_NAME,
            value=DEMO_BOOTSTRAP_SECRET_VALUE,
        )
    ]
    assert messages == [
        f"missing {secrets_file} Proceeding with a demo bootstrap marker secret for tenant 'm8flow'."
    ]


def test_m8flow_alias_is_resolved_to_current_tenant_id(tmp_path: Path) -> None:
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        "tenants:\n  m8flow:\n    secrets:\n      API_TOKEN: demo-token\n",
        encoding="utf-8",
    )

    secrets = load_seeded_secret_specs(
        secrets_file,
        organization_alias="m8flow",
        organization_id="tenant-123",
        missing_file_message_factory=lambda path: f"missing {path}",
    )

    assert secrets == [
        SeededSecretSpec(
            tenant_reference="m8flow",
            tenant_id="tenant-123",
            secret_name="API_TOKEN",
            value="demo-token",
        )
    ]


def test_present_file_with_empty_tenant_secret_mapping_is_rejected(tmp_path: Path) -> None:
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        "tenants:\n  m8flow:\n    secrets: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="must define at least one secret"):
        load_seeded_secret_specs(
            secrets_file,
            organization_alias="m8flow",
            organization_id="tenant-123",
            missing_file_message_factory=lambda path: f"missing {path}",
        )

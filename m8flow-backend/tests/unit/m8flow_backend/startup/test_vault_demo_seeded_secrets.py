from __future__ import annotations
# ruff: noqa: E402

import sys
from pathlib import Path
from io import BytesIO
from urllib.error import HTTPError

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
import bootstrap_vault_demo
import verify_backend_vault_demo


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


def test_bootstrap_main_failure_output_hides_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(bootstrap_vault_demo, "wait_for_vault_status", lambda: (_ for _ in ()).throw(
        RuntimeError("secret_id=secret-123 role_id=role-456 root_token=root-789 value=demo-secret")
    ))

    result = bootstrap_vault_demo.main()

    captured = capsys.readouterr()
    assert result == 1
    assert captured.err.strip() == "vault-demo: Bootstrap failed."
    assert "secret-123" not in captured.err
    assert "role-456" not in captured.err
    assert "root-789" not in captured.err
    assert "demo-secret" not in captured.err


def test_vault_request_error_suppresses_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=10):
        del timeout
        raise HTTPError(
            req.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=BytesIO(b'{"errors":["bad request"],"secret_id":"secret-123"}'),
        )

    monkeypatch.setattr(bootstrap_vault_demo.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        bootstrap_vault_demo.vault_request("GET", "sys/mounts", expected_statuses=(200,))

    message = str(exc_info.value)
    assert "secret-123" not in message
    assert "Response body suppressed to avoid logging sensitive data." in message


def test_verify_script_failure_output_hides_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(verify_backend_vault_demo, "load_env_file", lambda path: None)

    def fail_with_sensitive_details(**kwargs) -> None:
        del kwargs
        raise RuntimeError("secret_id=secret-123 value=demo-secret")

    monkeypatch.setattr(
        verify_backend_vault_demo,
        "wait_for_demo_tenant_identity",
        fail_with_sensitive_details,
    )

    result = verify_backend_vault_demo.main()

    captured = capsys.readouterr()
    assert result == 1
    assert "secret-123" not in captured.err
    assert "demo-secret" not in captured.err
    assert "RuntimeError" in captured.err

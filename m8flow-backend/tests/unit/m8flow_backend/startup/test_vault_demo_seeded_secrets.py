from __future__ import annotations
# ruff: noqa: E402

import sys
from pathlib import Path
from io import BytesIO
from types import ModuleType
from urllib.error import HTTPError

import pytest

backend_root = Path(__file__).resolve().parents[4]
repo_root = backend_root.parent
demo_src = repo_root / "docker" / "vault" / "demo"

demo_src_str = str(demo_src)
if demo_src_str not in sys.path:
    sys.path.insert(0, demo_src_str)

from seeded_secrets import (
    SeededSecretSpec,
    load_seeded_secret_specs,
)
import bootstrap_vault_demo
import verify_backend_vault_demo


def test_missing_secrets_file_skips_demo_seeding(tmp_path: Path) -> None:
    messages: list[str] = []
    secrets_file = tmp_path / "secrets.yml"

    secrets = load_seeded_secret_specs(
        secrets_file,
        organization_alias="m8flow",
        organization_id="tenant-123",
        missing_file_message_factory=lambda path: f"missing {path}",
        logger=messages.append,
    )

    assert secrets == []
    assert messages == [
        f"missing {secrets_file} Proceeding without seeding any demo secrets for tenant 'm8flow'."
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


def test_bootstrap_main_failure_output_logs_safe_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(bootstrap_vault_demo, "STATE_DIR", tmp_path / "vault-demo-state")
    monkeypatch.setattr(bootstrap_vault_demo, "wait_for_vault_status", lambda: (_ for _ in ()).throw(
        RuntimeError("secret_id=secret-123 role_id=role-456 root_token=root-789 value=demo-secret")
    ))

    result = bootstrap_vault_demo.main()

    captured = capsys.readouterr()
    assert result == 1
    assert captured.err.strip() == (
        "vault-demo: Bootstrap failed: RuntimeError: "
        "secret_id=[redacted] role_id=[redacted] root_token=[redacted] value=[redacted]"
    )


def test_load_seeded_secrets_missing_file_skips_demo_identity_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secrets_file = tmp_path / "secrets.yml"

    monkeypatch.setattr(bootstrap_vault_demo, "SECRETS_FILE", secrets_file)
    monkeypatch.setattr(
        bootstrap_vault_demo,
        "wait_for_demo_tenant_identity",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    assert bootstrap_vault_demo.load_seeded_secrets() == []


def test_verify_bootstrap_without_seeded_secrets_resolves_demo_tenant_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBrokerClient:
        def __init__(self, settings=None):
            self.settings = settings

        def check_availability(self):
            return True

        def retrieve_secret(self, path):
            assert path == "tenants/tenant-123/secrets/__vault_demo_probe__"
            return None

    class FakeTenantVaultClient:
        def list_secret_names(self, path):
            assert path == "tenants/tenant-123/secrets"
            return []

    class FakeTenantScopedClient:
        vault_client = FakeTenantVaultClient()

    class FakeProvider:
        def __init__(self, *, broker_vault_client):
            self.broker_vault_client = broker_vault_client

        def for_tenant(self, tenant_id):
            assert tenant_id == "tenant-123"
            return FakeTenantScopedClient()

    class FakeProvisioner:
        def __init__(self, *, vault_client):
            self.vault_client = vault_client

        def provision_tenant_identity(self, tenant_id):
            assert tenant_id == "tenant-123"
            return object()

    monkeypatch.setattr(
        bootstrap_vault_demo,
        "wait_for_vault_status",
        lambda: {"initialized": True, "sealed": False},
    )
    monkeypatch.setattr(bootstrap_vault_demo, "resolve_demo_tenant_identity", lambda: ("m8flow", "tenant-123"))
    monkeypatch.setenv("M8FLOW_BACKEND_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(bootstrap_vault_demo, "ROLE_ID_FILE", Path("/tmp/role-id"))
    monkeypatch.setattr(bootstrap_vault_demo, "SECRET_ID_FILE", Path("/tmp/secret-id"))

    fake_provider_module = ModuleType("m8flow_backend.services.tenant_scoped_vault_client_provider")
    fake_provider_module.TenantScopedVaultClientProvider = FakeProvider
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.tenant_scoped_vault_client_provider",
        fake_provider_module,
    )

    fake_provisioning_module = ModuleType("m8flow_backend.services.tenant_vault_provisioning_service")
    fake_provisioning_module.TenantVaultProvisioningService = FakeProvisioner
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.tenant_vault_provisioning_service",
        fake_provisioning_module,
    )

    fake_vault_client_module = ModuleType("m8flow_backend.services.vault_client")
    fake_vault_client_module.VaultClient = FakeBrokerClient
    fake_vault_client_module.VaultClientError = RuntimeError
    fake_vault_client_module.VaultSettings = type("VaultSettings", (), {"from_env": staticmethod(lambda: object())})
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.vault_client",
        fake_vault_client_module,
    )

    bootstrap_vault_demo.verify_bootstrap([])


def test_cleanup_legacy_demo_bootstrap_secret_deletes_marker_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_secret = SeededSecretSpec(
        tenant_reference="m8flow",
        tenant_id="tenant-123",
        secret_name="_m8flow_demo_bootstrap",
        value="",
    )

    monkeypatch.setattr(bootstrap_vault_demo, "resolve_demo_tenant_identity", lambda: ("m8flow", "tenant-123"))
    monkeypatch.setattr(
        bootstrap_vault_demo,
        "read_secret_value",
        lambda secret, token, allow_missing=False: "initialized" if secret == legacy_secret else None,
    )

    deleted: list[tuple[str, str, tuple[int, ...]]] = []

    def fake_vault_request(method, api_path, *, token=None, payload=None, expected_statuses=(200,)):
        del payload
        deleted.append((method, api_path, expected_statuses))
        return 204, None, ""

    monkeypatch.setattr(bootstrap_vault_demo, "vault_request", fake_vault_request)

    assert bootstrap_vault_demo.cleanup_legacy_demo_bootstrap_secret("root-token") is True
    assert deleted == [
        (
            "DELETE",
            "kv/metadata/m8flow/tenants/tenant-123/secrets/_m8flow_demo_bootstrap",
            (200, 204),
        )
    ]


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


def test_initialize_if_needed_uses_extended_init_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_timeout: float | None = None

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        def getcode(self):
            return 200

        def read(self):
            return b'{"root_token":"root-123","keys_base64":["unseal-456"]}'

    def fake_urlopen(req, timeout=10):
        del req
        nonlocal observed_timeout
        observed_timeout = timeout
        return FakeResponse()

    monkeypatch.setenv("M8FLOW_BACKEND_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(bootstrap_vault_demo, "STATE_DIR", tmp_path / "vault-demo-state")
    monkeypatch.setattr(bootstrap_vault_demo, "INIT_FILE", (tmp_path / "vault-demo-state") / "init.json")
    monkeypatch.setattr(bootstrap_vault_demo, "ROLE_ID_FILE", (tmp_path / "vault-demo-state") / "m8flow-role-id")
    monkeypatch.setattr(bootstrap_vault_demo, "SECRET_ID_FILE", (tmp_path / "vault-demo-state") / "m8flow-secret-id")
    monkeypatch.setattr(bootstrap_vault_demo, "RUNTIME_ENV_FILE", (tmp_path / "vault-demo-state") / "runtime.env")
    monkeypatch.setattr(bootstrap_vault_demo, "VERIFICATION_FILE", (tmp_path / "vault-demo-state") / "verification.json")
    monkeypatch.setattr(bootstrap_vault_demo, "INIT_REQUEST_TIMEOUT_SECONDS", 60.0)
    monkeypatch.setattr(bootstrap_vault_demo.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(bootstrap_vault_demo, "wait_for_vault_status", lambda: {"initialized": True, "sealed": False})

    status = bootstrap_vault_demo.initialize_if_needed({"initialized": False, "sealed": False})

    assert observed_timeout == 60.0
    assert status == {"initialized": True, "sealed": False}
    assert bootstrap_vault_demo.load_encrypted_json_file(bootstrap_vault_demo.INIT_FILE) == {
        "root_token": "root-123",
        "keys_base64": ["unseal-456"],
    }


def test_bootstrap_encrypted_state_files_do_not_store_plaintext(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("M8FLOW_BACKEND_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
    payload = {"root_token": "root-123", "keys_base64": ["unseal-456"]}
    target_file = tmp_path / "init.json"

    bootstrap_vault_demo.write_encrypted_json_file(target_file, payload)

    raw_text = target_file.read_text(encoding="utf-8")
    assert "root-123" not in raw_text
    assert "unseal-456" not in raw_text
    assert raw_text.startswith("m8flow-vault-demo:enc:v1:")
    assert bootstrap_vault_demo.load_encrypted_json_file(target_file) == payload


def test_verification_report_does_not_store_secret_derived_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_file = tmp_path / "verification.json"
    monkeypatch.setattr(bootstrap_vault_demo, "VERIFICATION_FILE", report_file)

    bootstrap_vault_demo.write_verification_report(broker_direct_read_blocked=True)

    assert report_file.read_text(encoding="utf-8") == '{\n  "broker_direct_read_blocked": true,\n  "verified": true\n}\n'


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
    assert captured.err.strip() == "vault-demo-verify failed."


def test_verify_script_success_output_is_generic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("", encoding="utf-8")
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        "tenants:\n  m8flow:\n    secrets:\n      API_TOKEN: demo-token\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("M8FLOW_VAULT_DEMO_ENV_FILE", str(runtime_env))
    monkeypatch.setenv("M8FLOW_VAULT_DEMO_SECRETS_FILE", str(secrets_file))

    fake_identity = type(
        "Identity",
        (),
        {
            "admin_username": "admin",
            "organization_alias": "m8flow",
            "organization_id": "tenant-123",
        },
    )()

    fake_broker_client = type(
        "BrokerClient",
        (),
        {
            "settings": type("Settings", (), {"mount_point": "kv", "secret_path_prefix": "m8flow"})(),
            "check_availability": lambda self: True,
            "retrieve_secret": lambda self, path: None,
        },
    )()
    fake_tenant_client = type(
        "TenantClient",
        (),
        {
            "vault_client": type(
                "TenantVaultClient",
                (),
                {"retrieve_secret": lambda self, path: "demo-token"},
            )()
        },
    )()

    monkeypatch.setattr(verify_backend_vault_demo, "wait_for_demo_tenant_identity", lambda **kwargs: fake_identity)
    monkeypatch.setattr(
        verify_backend_vault_demo,
        "load_env_file",
        lambda path: None,
    )
    fake_provisioning_module = ModuleType("m8flow_backend.services.tenant_vault_provisioning_service")

    class FakeProvisioner:
        def __init__(self, *, vault_client):
            self.vault_client = vault_client

        def provision_tenant_identity(self, tenant_id):
            del tenant_id
            return type("ProvisionedIdentity", (), {"policy_name": "policy", "role_name": "role"})()

    fake_provisioning_module.TenantVaultProvisioningService = FakeProvisioner
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.tenant_vault_provisioning_service",
        fake_provisioning_module,
    )

    fake_provider_module = ModuleType("m8flow_backend.services.tenant_scoped_vault_client_provider")

    class FakeProvider:
        def __init__(self, *, broker_vault_client):
            self.broker_vault_client = broker_vault_client

        def for_tenant(self, tenant_id):
            del tenant_id
            return fake_tenant_client

    fake_provider_module.TenantScopedVaultClientProvider = FakeProvider
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.tenant_scoped_vault_client_provider",
        fake_provider_module,
    )

    fake_vault_client_module = ModuleType("m8flow_backend.services.vault_client")
    fake_vault_client_module.VaultClient = lambda settings=None: fake_broker_client
    fake_vault_client_module.VaultClientError = RuntimeError
    fake_vault_client_module.VaultSettings = type("VaultSettings", (), {"from_env": staticmethod(lambda: object())})
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.vault_client",
        fake_vault_client_module,
    )

    result = verify_backend_vault_demo.main()

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == "vault-demo-verify: Verification succeeded."
    assert "json" not in captured.out.lower()
    assert "tenant-123" not in captured.out

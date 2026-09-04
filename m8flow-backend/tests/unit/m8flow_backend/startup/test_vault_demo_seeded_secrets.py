from __future__ import annotations
# ruff: noqa: E402

import importlib.util
import socket
import sys
from pathlib import Path
from io import BytesIO
from types import ModuleType
from urllib.error import HTTPError, URLError

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
import seed_named_values
import verify_backend_vault_demo


def test_vault_demo_seed_uses_internal_database_without_running_migrations() -> None:
    """The seed container imports the app and must use the Compose DB service."""
    compose = (repo_root / "docker" / "m8flow-docker-compose.yml").read_text(encoding="utf-8")
    seed_block = compose.split("  vault-demo-seed:\n", 1)[1].split("  m8flow-nats-consumer:\n", 1)[0]

    assert "@m8flow-db:5432/" in seed_block
    assert 'M8FLOW_BACKEND_UPGRADE_DB: "false"' in seed_block
    assert 'M8FLOW_BACKEND_SW_UPGRADE_DB: "false"' in seed_block
    assert 'profiles: ["vault-demo"]' in seed_block
    assert 'm8flow-backend:\n        condition: service_started' in seed_block
    assert 'vault-demo:\n        condition: service_started' in seed_block
    assert 'M8FLOW_VAULT_DEMO_BACKEND_URL: "http://m8flow-backend:6840"' in seed_block
    assert 'M8FLOW_VAULT_DEMO_SEED_WAIT_TIMEOUT_SECONDS' in seed_block
    assert 'M8FLOW_VAULT_DEMO_VERIFY_LIST_API: "true"' in seed_block


def test_wait_for_backend_ready_retries_until_status_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(_request, timeout):
        del timeout
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise URLError("not ready")
        return FakeResponse()

    monkeypatch.setattr(seed_named_values.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(seed_named_values.time, "sleep", lambda _seconds: None)

    seed_named_values.wait_for_backend_ready()

    assert attempts == 2


def test_authenticated_list_api_verifies_safe_seeded_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            import json

            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(call, timeout):
        del timeout
        requests.append(call)
        if len(requests) == 1:
            return FakeResponse({"access_token": "token"})
        return FakeResponse(
            {
                "values": [
                    {
                        "name": "API_TOKEN",
                        "tenantId": "tenant-123",
                        "isSensitive": True,
                        "isConfigured": True,
                        "value": None,
                    }
                ]
            }
        )

    monkeypatch.setattr(seed_named_values.request, "urlopen", fake_urlopen)

    seed_named_values.verify_authenticated_list_api([_seeded_secret()], "tenant-123")

    assert len(requests) == 2


def _load_isolated_bootstrap_module(module_name: str) -> ModuleType:
    module_path = demo_src / "bootstrap_vault_demo.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


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


@pytest.mark.parametrize(
    "contents",
    ["", "   \n", "tenants: {}\n", "tenants:\n  m8flow:\n    secrets: {}\n"],
)
def test_empty_seed_files_skip_seeding(tmp_path: Path, contents: str) -> None:
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(contents, encoding="utf-8")

    assert load_seeded_secret_specs(
        secrets_file,
        organization_alias="m8flow",
        organization_id="tenant-123",
        missing_file_message_factory=lambda path: f"missing {path}",
    ) == []


def test_seed_file_with_only_empty_noncanonical_tenant_skips_seeding(tmp_path: Path) -> None:
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text("tenants:\n  other:\n    secrets: {}\n", encoding="utf-8")

    assert load_seeded_secret_specs(
        secrets_file,
        organization_alias="m8flow",
        organization_id="tenant-123",
        missing_file_message_factory=lambda path: f"missing {path}",
    ) == []


def test_seed_file_rejects_case_insensitive_duplicate_names(tmp_path: Path) -> None:
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        "tenants:\n  m8flow:\n    secrets:\n      API_TOKEN: first\n      api_token: second\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="duplicate configuration-variable names"):
        load_seeded_secret_specs(
            secrets_file,
            organization_alias="m8flow",
            organization_id="tenant-123",
            missing_file_message_factory=lambda path: f"missing {path}",
        )


def test_seed_file_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    secrets_file = tmp_path / "secrets.yml"
    secrets_file.write_text(
        "tenants:\n  m8flow:\n    secrets:\n      API_TOKEN: first\n      API_TOKEN: second\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="duplicate mapping key"):
        load_seeded_secret_specs(
            secrets_file,
            organization_alias="m8flow",
            organization_id="tenant-123",
            missing_file_message_factory=lambda path: f"missing {path}",
        )


class _SeededRow:
    def __init__(self, name: str, *, sensitive: bool = True) -> None:
        self.id = f"id-{name.lower()}"
        self.name = name
        self.description = "existing description"
        self.is_sensitive = sensitive
        self.value = None if sensitive else "non-sensitive"
        self.is_configured = True


class _SeededNamedValueService:
    rows: list[_SeededRow] = []
    created: list[tuple[object, ...]] = []
    updated: list[tuple[object, ...]] = []

    @classmethod
    def reset(cls, rows: list[_SeededRow] | None = None) -> None:
        cls.rows = list(rows or [])
        cls.created = []
        cls.updated = []

    @staticmethod
    def _normalized_name(name: str) -> str:
        return name.strip()

    @classmethod
    def list_values(cls, _tenant_id: str) -> list[_SeededRow]:
        return cls.rows

    @classmethod
    def create_value(cls, *args, **kwargs) -> _SeededRow:
        cls.created.append((*args, kwargs))
        row = _SeededRow(args[2])
        cls.rows.append(row)
        return row

    @classmethod
    def update_value(cls, *args, **kwargs) -> _SeededRow:
        cls.updated.append((*args, kwargs))
        row = args[0]
        row.is_sensitive = kwargs["is_sensitive"]
        row.value = None
        return row

    @classmethod
    def resolve_value(cls, row: _SeededRow) -> str:
        del row
        return "configured"


def _seeded_secret(name: str = "API_TOKEN", value: str = "demo-value") -> SeededSecretSpec:
    return SeededSecretSpec("m8flow", "tenant-123", name, value)


def test_seed_reconciliation_creates_catalog_entry_without_persisting_plaintext() -> None:
    _SeededNamedValueService.reset()

    result = seed_named_values.reconcile_seeded_values(
        [_seeded_secret()],
        user_id=7,
        overwrite=False,
        named_value_service=_SeededNamedValueService,
    )

    assert result == seed_named_values.SeedResult(created=1)
    assert _SeededNamedValueService.created == [
        (
            "tenant-123",
            7,
            "API_TOKEN",
            "demo-value",
            "Seeded for local Vault development.",
            {"is_sensitive": True, "allow_unattributed_sensitive": True},
        )
    ]
    assert _SeededNamedValueService.rows[0].value is None


def test_seed_verification_requires_sensitive_catalog_rows_and_provider_values() -> None:
    row = _SeededRow("API_TOKEN")
    _SeededNamedValueService.reset([row])

    storage = type("Storage", (), {"read_document": lambda self, _row: {"value": "configured"}})()
    seed_named_values.verify_seeded_values(
        [_seeded_secret()], named_value_service=_SeededNamedValueService, storage=storage
    )

    row.is_configured = False
    with pytest.raises(RuntimeError, match="catalog verification"):
        seed_named_values.verify_seeded_values(
            [_seeded_secret()], named_value_service=_SeededNamedValueService, storage=storage
        )


def test_seed_reconciliation_is_idempotent_and_preserves_existing_sensitive_value() -> None:
    _SeededNamedValueService.reset([_SeededRow("API_TOKEN")])

    result = seed_named_values.reconcile_seeded_values(
        [_seeded_secret(value="replacement")],
        user_id=7,
        overwrite=False,
        named_value_service=_SeededNamedValueService,
    )

    assert result == seed_named_values.SeedResult(reused=1)
    assert _SeededNamedValueService.created == []
    assert _SeededNamedValueService.updated == []


def test_seed_reconciliation_overwrites_only_when_enabled() -> None:
    existing = _SeededRow("API_TOKEN")
    _SeededNamedValueService.reset([existing])

    result = seed_named_values.reconcile_seeded_values(
        [_seeded_secret(value="replacement")],
        user_id=7,
        overwrite=True,
        named_value_service=_SeededNamedValueService,
    )

    assert result == seed_named_values.SeedResult(updated=1)
    assert len(_SeededNamedValueService.updated) == 1
    _args = _SeededNamedValueService.updated[0]
    assert _args[0] is existing
    assert _args[-1]["value"] == "replacement"
    assert _args[-1]["is_sensitive"] is True


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


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("M8FLOW_VAULT_DEMO_HTTP_TIMEOUT_SECONDS", "not-a-number"),
        ("M8FLOW_VAULT_DEMO_INIT_TIMEOUT_SECONDS", " "),
    ],
)
def test_bootstrap_import_rejects_invalid_float_env_values(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(RuntimeError, match=rf"{env_name} must be a finite number greater than 0;"):
        _load_isolated_bootstrap_module(f"bootstrap_vault_demo_invalid_{env_name.lower()}")


def test_float_env_returns_default_for_unset_and_empty_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("M8FLOW_TEST_FLOAT_ENV", raising=False)
    assert bootstrap_vault_demo._float_env("M8FLOW_TEST_FLOAT_ENV", 12.5, min_value=0.0) == 12.5

    monkeypatch.setenv("M8FLOW_TEST_FLOAT_ENV", "")
    assert bootstrap_vault_demo._float_env("M8FLOW_TEST_FLOAT_ENV", 12.5, min_value=0.0) == 12.5


def test_float_env_rejects_whitespace_only_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("M8FLOW_TEST_FLOAT_ENV", "   ")

    with pytest.raises(RuntimeError, match=r"M8FLOW_TEST_FLOAT_ENV must be a finite number greater than 0;"):
        bootstrap_vault_demo._float_env("M8FLOW_TEST_FLOAT_ENV", 12.5, min_value=0.0)


@pytest.mark.parametrize("env_value", ["nan", "inf", "-inf"])
def test_float_env_rejects_non_finite_values(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
) -> None:
    monkeypatch.setenv("M8FLOW_TEST_FLOAT_ENV", env_value)

    with pytest.raises(RuntimeError, match=r"M8FLOW_TEST_FLOAT_ENV must be a finite number greater than 0;"):
        bootstrap_vault_demo._float_env("M8FLOW_TEST_FLOAT_ENV", 12.5, min_value=0.0)


@pytest.mark.parametrize("env_value", ["0", "-1", "-0.01"])
def test_float_env_rejects_zero_and_negative_values_when_minimum_is_zero(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
) -> None:
    monkeypatch.setenv("M8FLOW_TEST_FLOAT_ENV", env_value)

    with pytest.raises(RuntimeError, match=r"M8FLOW_TEST_FLOAT_ENV must be a finite number greater than 0;"):
        bootstrap_vault_demo._float_env("M8FLOW_TEST_FLOAT_ENV", 12.5, min_value=0.0)


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
    tmp_path: Path,
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
    monkeypatch.setattr(bootstrap_vault_demo, "VERIFICATION_FILE", tmp_path / "verification.json")

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


def test_vault_request_urlerror_timeout_uses_timeout_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req, timeout=10):
        del req, timeout
        raise URLError(socket.timeout("timed out"))

    monkeypatch.setattr(bootstrap_vault_demo.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=r"Vault API GET /v1/sys/mounts timed out after 7s\."):
        bootstrap_vault_demo.vault_request("GET", "sys/mounts", expected_statuses=(200,), timeout_seconds=7.0)


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

    monkeypatch.setattr(verify_backend_vault_demo, "ensure_backend_src_on_path", fail_with_sensitive_details)

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

    class FakeFlaskApp:
        def app_context(self):
            from contextlib import nullcontext

            return nullcontext()

        def test_request_context(self, _path):
            from contextlib import nullcontext

            return nullcontext()

    fake_app_module = ModuleType("m8flow_backend.app")
    fake_app_module.app = FakeFlaskApp()
    monkeypatch.setitem(sys.modules, "m8flow_backend.app", fake_app_module)

    fake_flask_module = ModuleType("flask")
    fake_flask_module.g = type("G", (), {})()
    monkeypatch.setitem(sys.modules, "flask", fake_flask_module)

    seeded_row = type(
        "SeededRow",
        (),
        {
            "id": "named-value-123",
            "name": "API_TOKEN",
            "m8f_tenant_id": "tenant-123",
            "is_sensitive": True,
            "is_configured": True,
            "value": None,
        },
    )()

    class FakeQuery:
        def filter_by(self, **kwargs):
            assert kwargs == {"m8f_tenant_id": "tenant-123"}
            return self

        def all(self):
            return [seeded_row]

    fake_named_value_module = ModuleType("m8flow_backend.models.named_value")
    fake_named_value_module.NamedValueModel = type("NamedValueModel", (), {"query": FakeQuery()})
    monkeypatch.setitem(sys.modules, "m8flow_backend.models.named_value", fake_named_value_module)

    fake_config_module = ModuleType("m8flow_backend.config")
    fake_config_module.default_organization_alias = lambda: "m8flow"
    monkeypatch.setitem(sys.modules, "m8flow_backend.config", fake_config_module)

    fake_shared_realm_module = ModuleType("m8flow_backend.startup.shared_realm_bootstrap")
    fake_shared_realm_module.resolve_default_shared_realm_tenant_id = lambda: "tenant-123"
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.startup.shared_realm_bootstrap",
        fake_shared_realm_module,
    )

    fake_storage_module = ModuleType("m8flow_backend.services.named_value_secret_storage")

    class FakeStorage:
        def read_document(self, row):
            assert row is seeded_row
            return {"value": "demo-token"}

    fake_storage_module.VaultNamedValueSecretStorage = FakeStorage
    fake_storage_module.vault_provider_key = (
        lambda tenant_id, value_id: f"tenants/{tenant_id}/secrets/configuration-variable/{value_id}"
    )
    monkeypatch.setitem(
        sys.modules,
        "m8flow_backend.services.named_value_secret_storage",
        fake_storage_module,
    )

    result = verify_backend_vault_demo.main()

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip() == "vault-demo-verify: Verification succeeded."
    assert "json" not in captured.out.lower()
    assert "tenant-123" not in captured.out

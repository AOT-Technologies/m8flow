from __future__ import annotations

import importlib
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType


extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


class FakeSecret:
    def __init__(self, key: str, value: str = "enc:vault-value") -> None:
        self.key = key
        self.value = value


class FakeSecretBackend:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def add_secret(self, key: str, value: str, user_id: int):
        self.calls.append(("add_secret", key, value, user_id))
        return {"id": "secret-1", "key": key, "user_id": user_id}

    def get_secret(self, key: str) -> FakeSecret:
        self.calls.append(("get_secret", key))
        return FakeSecret(key=key)

    def update_secret(
        self,
        key: str,
        value: str,
        user_id: int | None = None,
        create_if_not_exists: bool | None = False,
    ) -> None:
        self.calls.append(("update_secret", key, value, user_id, create_if_not_exists))

    def delete_secret(self, key: str, user_id: int) -> None:
        self.calls.append(("delete_secret", key, user_id))


def _load_patch(monkeypatch, backend: FakeSecretBackend):
    fake_secret_service_module = ModuleType("spiffworkflow_backend.services.secret_service")

    class FakeSecretService:
        @staticmethod
        def add_secret(key: str, value: str, user_id: int):
            raise AssertionError("patch not applied")

        @staticmethod
        def get_secret(key: str):
            raise AssertionError("patch not applied")

        @staticmethod
        def update_secret(
            key: str,
            value: str,
            user_id: int | None = None,
            create_if_not_exists: bool | None = False,
        ) -> None:
            raise AssertionError("patch not applied")

        @staticmethod
        def delete_secret(key: str, user_id: int) -> None:
            raise AssertionError("patch not applied")

        @staticmethod
        def resolve_possibly_secret_value(value: str) -> str:
            raise AssertionError("patch not applied")

        @staticmethod
        def _decrypt(value: str) -> str:
            return value.removeprefix("enc:")

    fake_secret_service_module.SecretService = FakeSecretService

    fake_backend_module = ModuleType("m8flow_backend.services.secret_backend")
    fake_backend_module.get_secret_backend = lambda: backend

    fake_spiff_services = ModuleType("spiffworkflow_backend.services")
    fake_spiff_services.__path__ = []

    fake_sentry_sdk = ModuleType("sentry_sdk")
    fake_sentry_sdk.start_span = lambda **_kwargs: nullcontext()

    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services", fake_spiff_services)
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.services.secret_service", fake_secret_service_module)
    monkeypatch.setitem(sys.modules, "m8flow_backend.services.secret_backend", fake_backend_module)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    sys.modules.pop("m8flow_backend.services.secret_service_patch", None)
    patch_module = importlib.import_module("m8flow_backend.services.secret_service_patch")
    monkeypatch.setattr(patch_module, "_PATCHED", False)
    patch_module.apply()
    return FakeSecretService


def test_secret_service_patch_delegates_crud_to_common_backend(monkeypatch) -> None:
    backend = FakeSecretBackend()
    secret_service = _load_patch(monkeypatch, backend)

    created = secret_service.add_secret("API_TOKEN", "vault-value", 7)
    resolved = secret_service.get_secret("API_TOKEN")
    secret_service.update_secret("API_TOKEN", "rotated-value", user_id=9, create_if_not_exists=True)
    secret_service.delete_secret("API_TOKEN", 11)

    assert created == {"id": "secret-1", "key": "API_TOKEN", "user_id": 7}
    assert isinstance(resolved, FakeSecret)
    assert resolved.key == "API_TOKEN"
    assert backend.calls == [
        ("add_secret", "API_TOKEN", "vault-value", 7),
        ("get_secret", "API_TOKEN"),
        ("update_secret", "API_TOKEN", "rotated-value", 9, True),
        ("delete_secret", "API_TOKEN", 11),
    ]


def test_secret_service_patch_resolves_only_m8flow_secret_prefix(monkeypatch) -> None:
    backend = FakeSecretBackend()
    secret_service = _load_patch(monkeypatch, backend)

    resolved = secret_service.resolve_possibly_secret_value("Bearer M8FLOW_SECRET:API_TOKEN")
    untouched = secret_service.resolve_possibly_secret_value("Bearer SPIFF_SECRET:API_TOKEN")

    assert resolved == "Bearer vault-value"
    assert untouched == "Bearer SPIFF_SECRET:API_TOKEN"
    assert backend.calls == [("get_secret", "API_TOKEN")]

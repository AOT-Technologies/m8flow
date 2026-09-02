"""Safe metadata API tests for manual configuration variables."""

from __future__ import annotations

from flask import Flask

from m8flow_backend.routes import named_values_controller as controller


class _Value:
    def __init__(self, value_id: str) -> None:
        self.id = value_id

    def to_dict(self):
        return {
            "id": self.id,
            "name": "API_TOKEN",
            "description": "safe metadata",
            "value": None,
            "isSensitive": True,
            "isConfigured": True,
        }


def test_list_and_detail_are_catalog_only_and_do_not_resolve_vault(monkeypatch) -> None:
    app = Flask(__name__)
    calls: list[tuple[str, str]] = []
    value = _Value("immutable-id")

    monkeypatch.setattr(controller, "_tenant_id", lambda: "tenant-a")
    monkeypatch.setattr(
        controller.NamedValueService,
        "list_values",
        lambda tenant_id: calls.append(("list", tenant_id)) or [value],
    )
    monkeypatch.setattr(
        controller.NamedValueService,
        "get_value",
        lambda tenant_id, value_id: calls.append(("get", f"{tenant_id}:{value_id}")) or value,
    )
    monkeypatch.setattr(
        controller.NamedValueService,
        "resolve_value",
        lambda _row: (_ for _ in ()).throw(AssertionError("Vault must not be resolved")),
    )

    with app.test_request_context("/"):
        listed = controller.list_named_values()
        detailed = controller.get_named_value("immutable-id")

    assert listed.get_json()["values"] == [value.to_dict()]
    assert detailed.get_json() == value.to_dict()
    assert calls == [("list", "tenant-a"), ("get", "tenant-a:immutable-id")]

from types import SimpleNamespace

import pytest
from spiffworkflow_backend.exceptions.api_error import ApiError

from m8flow_backend.services import tenant_role_service


def _stub_create_group_dependencies(monkeypatch, *, existing_group_names=None):
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_for_tenant",
        lambda tenant_id: (
            SimpleNamespace(id=tenant_id, slug="tenant-slug"),
            {"id": "org-1"},
            "org-1",
        ),
    )
    monkeypatch.setattr(
        tenant_role_service,
        "_organization_group_name_lookup",
        lambda _organization_id: {
            name.casefold(): name for name in (existing_group_names or [])
        },
    )
    monkeypatch.setattr(
        tenant_role_service,
        "list_organization_group_members",
        lambda _organization_id, _group_id: [],
    )
    monkeypatch.setattr(
        tenant_role_service,
        "get_organization_group_by_id",
        lambda _organization_id, _group_id: None,
    )
    monkeypatch.setattr(
        tenant_role_service,
        "organization_group_role_names",
        lambda _group: [],
    )


def test_create_tenant_group_normalizes_whitespace_before_creation(monkeypatch):
    _stub_create_group_dependencies(monkeypatch)
    created_group_names: list[str] = []

    monkeypatch.setattr(
        tenant_role_service,
        "create_organization_group",
        lambda _organization_id, group_name: created_group_names.append(group_name)
        or {
            "id": "group-1",
            "name": group_name,
            "path": f"/{group_name}",
        },
    )

    created_group = tenant_role_service.create_tenant_group(
        "tenant-1",
        "  QA   Reviewers  ",
    )

    assert created_group_names == ["QA Reviewers"]
    assert created_group["name"] == "QA Reviewers"


def test_create_tenant_group_rejects_special_characters():
    with pytest.raises(ApiError) as exc_info:
        tenant_role_service.create_tenant_group("tenant-1", "Bad %#@! group")

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "invalid_group"
    assert (
        exc_info.value.message
        == "Group name can only contain letters, numbers, spaces, hyphens, and "
        "underscores, and must start and end with a letter or number."
    )


def test_create_tenant_group_rejects_overly_long_name():
    with pytest.raises(ApiError) as exc_info:
        tenant_role_service.create_tenant_group("tenant-1", "a" * 65)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "invalid_group"
    assert exc_info.value.message == "Group name must be 64 characters or fewer."


def test_create_tenant_group_detects_duplicate_after_normalization(monkeypatch):
    _stub_create_group_dependencies(
        monkeypatch,
        existing_group_names=["QA   Reviewers"],
    )

    with pytest.raises(ApiError) as exc_info:
        tenant_role_service.create_tenant_group("tenant-1", "  qa reviewers  ")

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "group_exists"
    assert (
        exc_info.value.message
        == "Group 'qa reviewers' already exists in the tenant organization."
    )

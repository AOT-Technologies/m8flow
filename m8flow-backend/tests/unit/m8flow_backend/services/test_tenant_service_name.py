import pytest

from m8flow_backend.services.tenant_service import INVALID_TENANT_NAME_MESSAGE, TenantService


@pytest.mark.parametrize("name", ["Acme", "Acme Corp", "Smith & Co.", "R&D-2", "my_tenant", "Zürich", "a" * 50])
def test_validate_name_accepts_supported_names(name):
    assert TenantService.validate_name(name) is None


@pytest.mark.parametrize("name", ["df45++!@$%^&$#*(*&", "sdsf#$$$!@@#", "-lead", "_x", "O'Neil", "a/b"])
def test_validate_name_rejects_special_characters(name):
    assert TenantService.validate_name(name) == INVALID_TENANT_NAME_MESSAGE


def test_validate_name_rejects_empty_and_too_long():
    assert TenantService.validate_name("") == "Tenant name cannot be empty."
    assert "50" in TenantService.validate_name("a" * 51)

from m8flow_backend.models.named_value import NamedValueModel
from m8flow_backend.services.named_value_service import NamedValueService


def test_sensitive_named_value_binds_empty_value_as_sql_null() -> None:
    """The storage constraint requires SQL NULL, not JSON's ``null`` literal."""
    assert NamedValueModel.__table__.c.value.type.none_as_null is True


def test_sensitive_named_value_service_uses_sql_null() -> None:
    stored_value = NamedValueService._stored_value("not-stored", True)

    assert str(stored_value) == "NULL"

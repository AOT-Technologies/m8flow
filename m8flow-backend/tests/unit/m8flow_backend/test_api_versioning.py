from __future__ import annotations

import pytest

from m8flow_backend.api_versioning import ApiVersion, resolve_api_version
from m8flow_backend.errors import ApiError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ApiVersion.V1),
        ("", ApiVersion.V1),
        ("  \t", ApiVersion.V1),
        ("1.0", ApiVersion.V1),
        (" 2.0 ", ApiVersion.V2),
    ],
)
def test_resolve_api_version_defaults_and_supported_values(value, expected):
    assert resolve_api_version(value) is expected


@pytest.mark.parametrize("value", ["v1", "v2", "3.0"])
def test_resolve_api_version_rejects_unsupported_values(value):
    with pytest.raises(ApiError) as exc_info:
        resolve_api_version(value)

    assert exc_info.value.error_code == "unsupported_api_version"
    assert exc_info.value.status_code == 400
    assert "1.0" in exc_info.value.message
    assert "2.0" in exc_info.value.message


def test_resolve_api_version_rejects_comma_separated_values():
    with pytest.raises(ApiError) as exc_info:
        resolve_api_version("1.0, 2.0")

    assert exc_info.value.error_code == "invalid_api_version_header"
    assert exc_info.value.status_code == 400

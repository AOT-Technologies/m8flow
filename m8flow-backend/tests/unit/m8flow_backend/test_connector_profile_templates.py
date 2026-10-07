"""Profile-form contract for connector templates.

The designer's Add/Edit profile form renders sections from ``groups``, masks
only ``type: "password"`` fields, and checks ``pattern`` before saving. These
pin the parts of that contract that fail silently in the UI.
"""

from __future__ import annotations

import re

import pytest

from m8flow_backend.connectors.templates import all_templates, template_for

_UPPERCASE_WORDS = {"URL", "ID", "API", "STARTTLS"}


@pytest.mark.parametrize("template", all_templates(), ids=lambda t: t["id"])
def test_profile_fields_belong_to_declared_sections(template: dict) -> None:
    declared = {group["id"] for group in template["groups"]}
    for field in template["profileFields"]:
        assert field["group"] in declared, (template["id"], field["id"])
        assert field["group"] in {"connection", "authentication"}, field["id"]


@pytest.mark.parametrize("template", all_templates(), ids=lambda t: t["id"])
def test_profile_field_labels_are_sentence_case(template: dict) -> None:
    for field in template["profileFields"]:
        words = field["label"].split()
        for word in words[1:]:
            assert word in _UPPERCASE_WORDS or word == word.lower(), field["label"]


@pytest.mark.parametrize("template", all_templates(), ids=lambda t: t["id"])
def test_only_highly_sensitive_fields_are_masked(template: dict) -> None:
    for field in template["profileFields"]:
        assert (field["type"] == "password") == bool(field["isHighlySensitive"]), field["id"]
        if "pattern" in field:
            re.compile(field["pattern"])
            # The designer compiles this with JS RegExp: reject Python-only
            # syntax that re.compile accepts but JS rejects or reads differently.
            assert not re.search(r"\(\?P|\(\?[aiLmsux]|\\[AZ]", field["pattern"]), field["id"]
            assert field["patternMessage"], field["id"]


@pytest.mark.parametrize(
    ("connector", "field_id", "good", "bad"),
    [
        ("stripe", "api_key", "sk_test_51Abc", "pk_live_51Abc"),
        ("slack", "token", "xoxb-123-456-abc", "xoxp-123"),
        ("smtp", "smtp_host", "smtp.example.com", "smtp://smtp.example.com:587"),
        ("postgres_v2", "database_connection_str", "host=db port=5432 dbname=app", "just-a-host"),
        ("postgres_v2", "database_connection_str", "postgresql://u:p@db:5432/app", "mysql://db"),
    ],
)
def test_profile_field_patterns(connector: str, field_id: str, good: str, bad: str) -> None:
    template = template_for(connector)
    assert template is not None
    field = next(f for f in template["profileFields"] if f["id"] == field_id)
    assert re.search(field["pattern"], good)
    assert not re.search(field["pattern"], bad)

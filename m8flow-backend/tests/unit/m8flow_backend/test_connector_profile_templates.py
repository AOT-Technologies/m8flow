"""Profile-form contract for connector templates.

The designer's Add/Edit profile form renders sections from ``groups``, masks
only ``type: "password"`` fields, and checks ``pattern`` before saving. These
pin the parts of that contract that fail silently in the UI.
"""

from __future__ import annotations

import re
import time

import pytest

from m8flow_backend.connectors.templates import all_templates, template_for

_UPPERCASE_WORDS = {"URL", "ID", "API", "STARTTLS"}


def _is_fully_anchored(pattern: str) -> bool:
    """``^...$`` with no top-level ``|`` (``^a|b$`` anchors each side only once)."""
    if not (pattern.startswith("^") and pattern.endswith("$") and not pattern.endswith("\\$")):
        return False
    depth, in_class, i = 0, False, 1
    while i < len(pattern) - 1:
        char = pattern[i]
        if char == "\\":
            i += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "|" and depth == 0:
            return False
        i += 1
    return True


def test_is_fully_anchored() -> None:
    assert _is_fully_anchored(r"^(sk|rk)_[a-z]+$")
    assert _is_fully_anchored(r"^[|]\|x$")
    assert not _is_fully_anchored(r"^sk_|rk_$")
    assert not _is_fully_anchored(r"sk_\w+$")
    assert not _is_fully_anchored(r"^sk_\w+")
    assert not _is_fully_anchored(r"^a\$")


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
            # The designer checks with JS RegExp.test (search semantics, like
            # re.search below), so a pattern only means "whole value" if anchored.
            assert _is_fully_anchored(field["pattern"]), field["id"]
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


@pytest.mark.parametrize("template", all_templates(), ids=lambda t: t["id"])
def test_profile_field_patterns_do_not_backtrack(template: dict) -> None:
    """The designer runs these patterns on every keystroke, so a pattern with
    catastrophic (exponential) or quadratic backtracking freezes the form on a
    long pasted value. Short inputs catch exponential blow-up without hanging
    CI; long ones catch quadratic (the old postgres pattern took ~800 ms here,
    linear ones take well under 10 ms)."""
    units = ("a", "a=", "a =", " ", "=", "-", ".", "_", "/:", "a\n")
    for field in template["profileFields"]:
        if "pattern" not in field:
            continue
        compiled = re.compile(field["pattern"])
        for length in (24, 20_000):
            for unit in units:
                value = unit * (length // len(unit)) + "\n!"
                started = time.perf_counter()
                compiled.search(value)
                elapsed = time.perf_counter() - started
                assert elapsed < 0.1, (field["id"], unit, length, f"{elapsed:.3f}s")

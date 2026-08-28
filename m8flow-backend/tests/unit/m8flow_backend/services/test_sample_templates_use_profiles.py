"""The shipped sample templates must get credentials from a connector profile.

These templates are the first thing a new tenant runs, so a hardcoded
credential reference in one of them is both a broken demo (there is no UI that
writes those flat keys any more) and a bad example to copy. This reads the
zips directly -- no database, no app context -- so it fails fast if a future
template edit reintroduces one.
"""

from __future__ import annotations

import glob
import os
import re
import zipfile

from m8flow_backend.services.connector_profile_migration import SECRET_KEY_TO_FIELD

SAMPLE_TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "sample_templates"
)

OPERATOR_RE = re.compile(
    r'<spiffworkflow:serviceTaskOperator\b[^>]*?\bid="([^"]+)"[^>]*?>'
    r"(.*?)"
    r"</spiffworkflow:serviceTaskOperator>",
    re.S,
)
PARAM_RE = re.compile(r'<spiffworkflow:parameter\b[^>]*?\bid="([^"]+)"([^>]*?)/>')

PROFILE_PARAMETER = "m8flow_profile"

# Parameter ids a profile supplies, keyed by connector type. Derived from the
# migration map so the two cannot drift.
PROFILE_SUPPLIED = {
    "smtp": {"smtp_host", "smtp_port", "smtp_user", "smtp_password", "email_from"},
    "slack": {"token", "channel"},
    "postgres_v2": {"database_connection_str"},
    "salesforce": {
        "instance_url",
        "access_token",
        "refresh_token",
        "client_id",
        "client_secret",
    },
    "stripe": {"api_key"},
}


def _service_tasks():
    """Yield (zip name, bpmn name, operator id, operator body) for every task."""
    pattern = os.path.join(SAMPLE_TEMPLATES_DIR, "*.zip")
    for zip_path in sorted(glob.glob(pattern)):
        with zipfile.ZipFile(zip_path) as archive:
            for entry in archive.namelist():
                if not entry.endswith(".bpmn"):
                    continue
                xml = archive.read(entry).decode("utf-8")
                for match in OPERATOR_RE.finditer(xml):
                    yield (
                        os.path.basename(zip_path),
                        entry,
                        match.group(1),
                        match.group(2),
                    )


def test_sample_templates_exist():
    """Guards the glob: an empty sweep would make every test below vacuous."""
    assert glob.glob(os.path.join(SAMPLE_TEMPLATES_DIR, "*.zip"))


def test_profile_supplied_parameters_carry_no_hardcoded_secret():
    offenders = []
    for zip_name, bpmn, operator_id, body in _service_tasks():
        supplied = PROFILE_SUPPLIED.get(operator_id.split("/")[0])
        if not supplied:
            continue
        for param_match in PARAM_RE.finditer(body):
            name, attrs = param_match.group(1), param_match.group(2)
            if name in supplied and "M8FLOW_SECRET" in attrs:
                offenders.append(f"{zip_name}:{bpmn} {operator_id}.{name}")
    assert not offenders, (
        "These parameters should come from a connector profile, not a hardcoded "
        "secret reference: " + ", ".join(offenders)
    )


def test_connector_tasks_reference_a_profile():
    missing = []
    for zip_name, bpmn, operator_id, body in _service_tasks():
        connector_type = operator_id.split("/")[0]
        if connector_type not in PROFILE_SUPPLIED:
            continue
        # Only tasks that actually need credentials must name a profile; a task
        # using none of the profile's fields legitimately has nothing to bind.
        uses_supplied = any(
            param_match.group(1) in PROFILE_SUPPLIED[connector_type]
            for param_match in PARAM_RE.finditer(body)
        )
        if uses_supplied and PROFILE_PARAMETER not in body:
            missing.append(f"{zip_name}:{bpmn} {operator_id}")
    assert not missing, (
        f"These service tasks need a '{PROFILE_PARAMETER}' parameter: "
        + ", ".join(missing)
    )


def test_profile_parameter_names_the_seeded_default():
    """The profile named must be the one the migration seeds, or nothing resolves."""
    from m8flow_backend.services.connector_profile_migration import (
        DEFAULT_PROFILE_NAME,
    )

    seen = 0
    for zip_name, bpmn, operator_id, body in _service_tasks():
        for param_match in PARAM_RE.finditer(body):
            if param_match.group(1) != PROFILE_PARAMETER:
                continue
            seen += 1
            # The value is a python expression, so the name arrives quoted.
            assert f"&#34;{DEFAULT_PROFILE_NAME}&#34;" in param_match.group(2), (
                f"{zip_name}:{bpmn} {operator_id} binds an unexpected profile: "
                f"{param_match.group(2)}"
            )
    assert seen, "no template references a connector profile"


def test_profile_supplied_names_are_known_definition_fields():
    """PROFILE_SUPPLIED must not drift from the connector definitions."""
    from m8flow_backend.connectors.registry import get_connector

    for connector_type, names in PROFILE_SUPPLIED.items():
        definition = get_connector(connector_type)
        assert definition is not None, f"unknown connector type {connector_type}"
        declared = set(definition.profile_field_names())
        unknown = names - declared
        assert not unknown, (
            f"{connector_type}: {sorted(unknown)} are not profile fields of "
            f"{definition.__name__}"
        )


def test_migration_map_covers_every_connector_used_by_templates():
    """A template connector with no migration entry cannot be auto-seeded."""
    used = set()
    for _zip_name, _bpmn, operator_id, body in _service_tasks():
        if PROFILE_PARAMETER in body:
            used.add(operator_id.split("/")[0])
    assert used, "no template references a connector profile"
    uncovered = used - set(SECRET_KEY_TO_FIELD)
    assert not uncovered, (
        f"templates bind profiles for {sorted(uncovered)}, but the migration map "
        f"cannot seed them from existing secrets"
    )

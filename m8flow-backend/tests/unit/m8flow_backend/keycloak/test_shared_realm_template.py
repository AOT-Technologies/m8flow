from __future__ import annotations

import json
from pathlib import Path


TEMPLATE_PATH = (
    Path(__file__).resolve().parents[4]
    / "keycloak"
    / "realm_exports"
    / "m8flow-tenant-template.json"
)


def test_shared_realm_template_disables_email_login_and_allows_duplicate_emails() -> None:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as template_file:
        realm_template = json.load(template_file)

    assert realm_template["organizationsEnabled"] is True
    assert realm_template["registrationEmailAsUsername"] is False
    assert realm_template["loginWithEmailAllowed"] is False
    assert realm_template["duplicateEmailsAllowed"] is True

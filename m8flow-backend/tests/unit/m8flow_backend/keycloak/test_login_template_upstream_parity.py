"""Pins login.ftl's socialProviders section to Keycloak's real base theme template
for the pinned version, and locks in the two documented m8flow additions.

login.ftl's own header comment claims it is byte-for-byte Keycloak's base theme
login.ftl (github.com/keycloak/keycloak, themes/src/main/resources/theme/base/
login/login.ftl) at the version m8flow-keycloak.Dockerfile / start_keycloak.sh
pin, with exactly two additions layered on top. This was verified directly against
that upstream file's actual content for the pinned version when the comment was
written; this test guards against silent drift going forward, in particular a
regression back to the old (bespoke, buggy) `numberOfIdps` / `identityProviders`
branching this file used to have before it was rewritten to match upstream exactly.

If the Keycloak version pin in start_keycloak.sh changes, re-diff this file against
the new tag's base theme login.ftl before touching these assertions.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
LOGIN_TEMPLATE_PATH = BACKEND_ROOT / "keycloak" / "themes" / "m8flow" / "login" / "login.ftl"
START_KEYCLOAK_SH_PATH = BACKEND_ROOT / "keycloak" / "start_keycloak.sh"


def _login_template() -> str:
    return LOGIN_TEMPLATE_PATH.read_text(encoding="utf-8")


def test_pinned_keycloak_version_is_documented_in_the_template_header() -> None:
    """The header comment names the pinned version explicitly; catch drift between
    the two rather than letting the comment silently go stale."""
    pinned_version = re.search(r"^keycloak_version=(\S+)", START_KEYCLOAK_SH_PATH.read_text(encoding="utf-8"), re.MULTILINE)
    assert pinned_version, "start_keycloak.sh must pin a keycloak_version"
    assert f"@ {pinned_version.group(1)}" in _login_template(), (
        "login.ftl's header comment must name the same Keycloak version pinned in "
        "start_keycloak.sh -- update the comment (and re-diff against that tag's "
        "base theme login.ftl) when the pin changes"
    )


def test_social_providers_section_matches_upstream_exactly() -> None:
    """No m8flow-specific branching in the socialProviders section: this must stay
    an exact copy of Keycloak's base theme guard/loop, not a bespoke reimplementation."""
    template = _login_template()

    # The bespoke numberOfIdps/identityProviders branching this file used to carry
    # (and which prompted this test) must never come back.
    assert "numberOfIdps" not in template
    assert "identityProviders" not in template

    # Upstream's exact guard and iteration target for the pinned version.
    assert "social?? && social.providers?has_content" in template
    assert '<#list social.providers as p>' in template
    assert 'id="social-${p.alias}"' in template


def test_m8flow_additions_are_still_present() -> None:
    """The two documented m8flow additions on top of the otherwise-verbatim upstream
    template; a future "align with upstream" edit must not drop these by mistake."""
    template = _login_template()

    assert "isM8flowRealmLogin" in template
    assert "m8f-hidden-username-login" in template

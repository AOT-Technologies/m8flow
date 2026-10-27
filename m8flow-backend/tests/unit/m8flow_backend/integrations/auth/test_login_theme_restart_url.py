"""safeHttpUrl in the login theme: follow same-origin and http(s) restart targets only."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[5]
    / "keycloak/themes/m8flow/login/resources/js/restartHiddenUsernameLogin.js"
)
CURRENT = "https://kc.example/realms/m8flow/login-actions/authenticate?x=1"

CASES = [
    # Keycloak's url.loginRestartFlowUrl is absolute; keep it as-is.
    (
        "https://kc.example/realms/m8flow/login-actions/restart?tab_id=b",
        "https://kc.example/realms/m8flow/login-actions/restart?tab_id=b",
    ),
    (
        "http://localhost:6842/realms/m8flow/login-actions/restart",
        "http://localhost:6842/realms/m8flow/login-actions/restart",
    ),
    # Relative targets stay on the current origin.
    ("/realms/m8flow/login-actions/restart?tab_id=b", "/realms/m8flow/login-actions/restart?tab_id=b"),
    ("/auth/realms/x/login-actions/restart", "/auth/realms/x/login-actions/restart"),
    ("restart?tab_id=b", "/realms/m8flow/login-actions/restart?tab_id=b"),
    # Script schemes and other-host tricks are refused.
    ("javascript:alert(1)", None),
    ("JaVaScRiPt:alert(1)", None),
    ("data:text/html,x", None),
    ("ftp://x/y", None),
    ("//evil.example/x", None),
    ("/\\evil.example/x", None),
    ("", None),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_safe_http_url_accepts_same_origin_and_http_targets_only():
    code = (
        f"import {{ safeHttpUrl }} from {json.dumps(SCRIPT.as_uri())};\n"
        f"const cases = {json.dumps([c[0] for c in CASES])};\n"
        f"console.log(JSON.stringify(cases.map((c) => safeHttpUrl(c, {json.dumps(CURRENT)}))));\n"
        # No window (e.g. pre-render): a root-relative path still works.
        "console.log(JSON.stringify(safeHttpUrl('/realms/m8flow/login-actions/restart', undefined)));\n"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    got_lines = result.stdout.strip().splitlines()
    assert json.loads(got_lines[0]) == [c[1] for c in CASES]
    assert json.loads(got_lines[1]) == "/realms/m8flow/login-actions/restart"

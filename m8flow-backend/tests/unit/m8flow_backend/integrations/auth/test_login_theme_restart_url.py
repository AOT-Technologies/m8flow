"""safeHttpUrl in the login theme: follow same-origin restart targets only."""

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
    # Keycloak renders url.loginRestartFlowUrl absolute, on the login page's own origin:
    # followed, as the equivalent root path.
    (
        "https://kc.example/realms/m8flow/login-actions/restart?tab_id=b",
        "/realms/m8flow/login-actions/restart?tab_id=b",
    ),
    ("HTTPS://KC.EXAMPLE/realms/m8flow/x", "/realms/m8flow/x"),
    # Absolute URLs on any other origin are refused (scheme, host and port all count).
    ("https://evil.example/realms/m8flow/login-actions/restart", None),
    ("http://kc.example/realms/m8flow/login-actions/restart", None),
    ("https://kc.example:8443/realms/m8flow/login-actions/restart", None),
    ("https://kc.example.evil.example/x", None),
    ("https://kc.example@evil.example/x", None),
    # Relative targets stay on the current origin.
    ("/realms/m8flow/login-actions/restart?tab_id=b", "/realms/m8flow/login-actions/restart?tab_id=b"),
    ("/auth/realms/x/login-actions/restart", "/auth/realms/x/login-actions/restart"),
    ("restart?tab_id=b", "/realms/m8flow/login-actions/restart?tab_id=b"),
    # Document-relative forms resolve against the current page exactly as the browser would.
    ("#frag", "/realms/m8flow/login-actions/authenticate?x=1#frag"),
    ("?q=1", "/realms/m8flow/login-actions/authenticate?q=1"),
    ("./restart?tab_id=b", "/realms/m8flow/login-actions/restart?tab_id=b"),
    ("../login-actions/restart", "/realms/m8flow/login-actions/restart"),
    ("../../../../x", "/x"),
    ("https://kc.example/a?b=1#h", "/a?b=1#h"),
    # Script schemes and other-host tricks are refused.
    ("javascript:alert(1)", None),
    ("JaVaScRiPt:alert(1)", None),
    ("data:text/html,x", None),
    ("ftp://x/y", None),
    ("//evil.example/x", None),
    ("/\\evil.example/x", None),
    # A path that normalizes to "//host" is collapsed so it cannot name another host.
    ("/.//evil.example/x", "/evil.example/x"),
    ("https://kc.example/.//evil.example/x", "/evil.example/x"),
    ("", None),
    # Delimiters in query and fragment keep their structure (hash routes, "+", encoded values).
    ("/r#/route?a=1&b=2", "/r#/route?a=1&b=2"),
    ("/r?q=a+b&n=%26x&u=%E2%9C%93", "/r?q=a+b&n=%26x&u=%E2%9C%93"),
    ("/a%2Fb/c?x=1:2@3", "/a%2Fb/c?x=1:2@3"),
    # Encoded delimiters stay encoded in path, query and fragment: tokens are split on the
    # raw text first and only then decoded, so "%2F", "%3F", "%26", "%3D", "%23", "%2B"
    # can never turn into structure.
    ("/a%3Fb%23c/d", "/a%3Fb%23c/d"),
    ("/r?next=%2Fa%2Fb%3Fx%3D1%26y%3D2%23h&p=%2B", "/r?next=%2Fa%2Fb%3Fx%3D1%26y%3D2%23h&p=%2B"),
    ("/r#/route?next=%2Fa%2Fb%3Fx%3D1%26y%3D2", "/r#/route?next=%2Fa%2Fb%3Fx%3D1%26y%3D2"),
    # Lower-case escapes are normalised to upper case (same octets).
    ("/r?next=%2fa", "/r?next=%2Fa"),
    # Raw unicode is percent-encoded the way the browser would send it.
    ("/r?u=✓", "/r?u=%E2%9C%93"),
    # A malformed escape anywhere is refused rather than guessed at.
    ("/a%zz/b", None),
    ("/r?q=%", None),
    ("/r#%E2%9C", None),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_safe_http_url_accepts_same_origin_targets_only(tmp_path):
    # Import a .mjs copy so Node treats it as an ES module on every version (no package.json here).
    module = tmp_path / "restartHiddenUsernameLogin.mjs"
    module.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    code = (
        f"import {{ safeHttpUrl }} from {json.dumps(module.as_uri())};\n"
        f"const cases = {json.dumps([c[0] for c in CASES])};\n"
        f"console.log(JSON.stringify(cases.map((c) => safeHttpUrl(c, {json.dumps(CURRENT)}))));\n"
        # No window (e.g. pre-render): a root-relative path still works; absolute and
        # document-relative targets cannot be checked against an origin, so they are refused.
        "console.log(JSON.stringify(safeHttpUrl('/realms/m8flow/login-actions/restart', undefined)));\n"
        "console.log(JSON.stringify(safeHttpUrl('https://kc.example/realms/m8flow/x', undefined)));\n"
        "console.log(JSON.stringify(safeHttpUrl('restart?x=1', undefined)));\n"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    got_lines = result.stdout.strip().splitlines()
    assert json.loads(got_lines[0]) == [c[1] for c in CASES]
    assert json.loads(got_lines[1]) == "/realms/m8flow/login-actions/restart"
    assert json.loads(got_lines[2]) is None
    assert json.loads(got_lines[3]) is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_refused_restart_url_shows_fallback_and_keeps_manual_link(tmp_path):
    # A refused URL (here a malformed escape) must not navigate or throw: the auto
    # restart shows the fallback, and the manual link falls back to its own href.
    module = tmp_path / "restartHiddenUsernameLogin.mjs"
    module.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    code = (
        f"import {{ restartHiddenUsernameLogin, handleManualHiddenUsernameRestart }} "
        f"from {json.dumps(module.as_uri())};\n"
        "const fallback = { hidden: true };\n"
        "globalThis.document = { getElementById: () => fallback };\n"
        "const marker = { getAttribute: (n) => (n === 'data-login-restart-url' ? '/a%zz' : null) };\n"
        "const replaced = [];\n"
        f"const loc = {{ href: {json.dumps(CURRENT)}, replace: (u) => replaced.push(u) }};\n"
        "const store = new Map();\n"
        "const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v),"
        " removeItem: (k) => store.delete(k) };\n"
        "const auto = restartHiddenUsernameLogin(marker, loc, storage);\n"
        "const manual = handleManualHiddenUsernameRestart(marker, loc, storage);\n"
        "console.log(JSON.stringify({ auto, manual, replaced, hidden: fallback.hidden }));\n"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) == {
        "auto": False,
        "manual": False,
        "replaced": [],
        "hidden": False,
    }

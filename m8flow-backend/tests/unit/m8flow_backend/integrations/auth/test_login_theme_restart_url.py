"""Exercise the inline login recovery script, including its URL trust boundary."""

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
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run_script(code):
    # Run the actual classic script unchanged, as a browser does. A separate VM
    # context also lets the URL tests inspect its lexical helpers without exports.
    result = subprocess.run(
        ["node"],
        input=(
            "const vm = require('node:vm');\n"
            "const fs = require('node:fs');\n"
            f"const source = fs.readFileSync({json.dumps(str(SCRIPT))}, 'utf8');\n"
            + code
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.strip().splitlines()]

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


def test_safe_http_url_accepts_same_origin_targets_only():
    code = (
        "vm.runInThisContext(source);\n"
        f"const cases = {json.dumps([c[0] for c in CASES])};\n"
        f"console.log(JSON.stringify(cases.map((c) => safeHttpUrl(c, {json.dumps(CURRENT)}))));\n"
        # No window (e.g. pre-render): a root-relative path still works; absolute and
        # document-relative targets cannot be checked against an origin, so they are refused.
        "console.log(JSON.stringify(safeHttpUrl('/realms/m8flow/login-actions/restart', undefined)));\n"
        "console.log(JSON.stringify(safeHttpUrl('https://kc.example/realms/m8flow/x', undefined)));\n"
        "console.log(JSON.stringify(safeHttpUrl('restart?x=1', undefined)));\n"
    )
    got = run_script(code)
    assert got[0] == [c[1] for c in CASES]
    assert got[1] == "/realms/m8flow/login-actions/restart"
    assert got[2] is None
    assert got[3] is None


def test_refused_restart_url_shows_fallback_and_keeps_manual_link():
    # A refused URL (here a malformed escape) must not navigate or throw: the auto
    # restart shows the fallback, and the manual link falls back to its own href.
    code = (
        "vm.runInThisContext(source);\n"
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
    assert run_script(code)[0] == {
        "auto": False,
        "manual": False,
        "replaced": [],
        "hidden": False,
    }


# Each page gets a fresh JS realm, while sessionStorage survives navigation.
# Throw if recovery waits for page readiness: unrelated modules can hold that
# event indefinitely on a slow network.
HARNESS = r"""
const store = new Map();
const key = 'm8flow-hidden-username-login-restart-url';
const pages = [];
function loadPage(options = {}) {
  const realm = options.realm || 'm8flow';
  const query = options.query || 'client_id=app&tab_id=tab&session_code=one';
  const restart = options.url || `/realms/${realm}/login-actions/restart?${query}`;
  const navigations = [];
  const status = { hidden: false };
  const fallback = { hidden: true };
  let listener;
  const link = {
    getAttribute: () => restart,
    addEventListener: (name, callback) => { listener = callback; },
  };
  const marker = { getAttribute: name => name === 'data-login-restart-url' ? restart : null };
  const elements = {
    'm8f-login-recovery-status': status,
    'm8f-hidden-username-login-fallback': fallback,
    'm8f-return-to-full-sign-in': link,
  };
  if (options.combined || options.reauth) {
    if (!options.reauth) elements.username = {};
    elements.password = {};
  } else {
    elements[options.marker || 'm8f-username-only-login'] = marker;
  }
  const storage = {
    getItem: k => {
      if (options.storage === 'read') throw new Error('SecurityError');
      return store.get(k) ?? null;
    },
    setItem: (k, v) => {
      if (options.storage === 'write') throw new Error('QuotaExceededError');
      store.set(k, v);
    },
    removeItem: k => {
      if (options.storage === 'remove') throw new Error('SecurityError');
      store.delete(k);
    },
  };
  const window = {
    location: {
      href: `https://kc.example/realms/${realm}/login-actions/authenticate?${query}`,
      replace: url => {
        if (options.navigationFails) throw new Error('Navigation failed');
        navigations.push(url);
      },
    },
    get sessionStorage() {
      if (options.storage === 'getter') throw new Error('SecurityError');
      if (options.storage === 'missing') return null;
      return storage;
    },
  };
  const document = {
    readyState: 'loading',
    getElementById: id => elements[id] || null,
    addEventListener: () => { throw new Error('Recovery waited for page readiness'); },
  };
  vm.runInNewContext(source, { window, document, URL });
  const page = {
    navigations, status, fallback,
    click: () => {
      let prevented = false;
      listener({ preventDefault: () => { prevented = true; } });
      return prevented;
    },
  };
  pages.push(page);
  return page;
}
"""


@pytest.mark.parametrize("realm", ["m8flow", "master"])
def test_recovery_starts_during_parsing_and_stops_after_two_restarts(realm):
    got = run_script(
        HARNESS
        + f"const options = {json.dumps({'realm': realm})};\n"
        + "loadPage(options);\n"
        + "loadPage({ ...options, query: 'client_id=app&tab_id=tab&session_code=two&execution=new' });\n"
        + "loadPage({ ...options, query: 'client_id=app&tab_id=tab&session_code=three' });\n"
        + "console.log(JSON.stringify(pages));\n"
    )[0]
    assert [len(page["navigations"]) for page in got] == [1, 1, 0]
    assert [page["fallback"]["hidden"] for page in got] == [True, True, False]
    assert [page["status"]["hidden"] for page in got] == [False, False, True]


@pytest.mark.parametrize(
    "options",
    [
        {"realm": "master"},
        {"query": "client_id=other&tab_id=tab"},
        {"query": "client_id=app&tab_id=another-tab"},
    ],
)
def test_distinct_login_context_gets_its_own_recovery_attempts(options):
    got = run_script(
        HARNESS
        + "loadPage(); loadPage();\n"
        + f"console.log(JSON.stringify(loadPage({json.dumps(options)})));\n"
    )[0]
    assert len(got["navigations"]) == 1
    assert got["fallback"]["hidden"] is True


def test_combined_form_clears_guard_and_manual_retry_resets_attempts():
    got = run_script(
        HARNESS
        + "loadPage(); loadPage();\n"
        + "const failed = loadPage();\n"
        + "const prevented = failed.click();\n"
        + "const reset = !store.has(key);\n"
        + "const retried = loadPage();\n"
        + "loadPage({ combined: true });\n"
        + "console.log(JSON.stringify({ prevented, reset, retried, cleared: !store.has(key) }));\n"
    )[0]
    assert got["prevented"] is True
    assert got["reset"] is True
    assert len(got["retried"]["navigations"]) == 1
    assert got["cleared"] is True


@pytest.mark.parametrize("failure", ["getter", "missing", "read", "write"])
def test_storage_failure_shows_retry_without_throwing(failure):
    got = run_script(
        HARNESS
        + f"const page = loadPage({{ storage: {json.dumps(failure)} }});\n"
        + "console.log(JSON.stringify({ page, prevented: page.click() }));\n"
    )[0]
    assert got["page"]["fallback"]["hidden"] is False
    assert got["page"]["status"]["hidden"] is True
    # Only the explicit user action navigates; it does not require storage.
    assert len(got["page"]["navigations"]) == 1
    assert got["prevented"] is True


def test_navigation_failure_keeps_native_manual_link_and_combined_form_tolerates_storage_failure():
    got = run_script(
        HARNESS
        + "const page = loadPage({ navigationFails: true });\n"
        + "const prevented = page.click();\n"
        + "loadPage({ combined: true, storage: 'remove' });\n"
        + "loadPage({ combined: true, storage: 'getter' });\n"
        + "console.log(JSON.stringify({ page, prevented }));\n"
    )[0]
    assert got["page"]["navigations"] == []
    assert got["page"]["fallback"]["hidden"] is False
    assert got["prevented"] is False


@pytest.mark.parametrize("legacy_json", [True, False])
def test_existing_restart_guard_cannot_bypass_limit(legacy_json):
    value = "/realms/m8flow/login-actions/restart?client_id=app&tab_id=tab&session_code=old"
    if legacy_json:
        value = json.dumps({"restartUrl": value, "attempts": 2})
    got = run_script(
        HARNESS
        + f"store.set(key, {json.dumps(value)});\n"
        + "console.log(JSON.stringify(loadPage()));\n"
    )[0]
    assert got["navigations"] == []
    assert got["fallback"]["hidden"] is False


def test_reauthentication_never_restarts_and_resets_the_counter():
    # prompt=login over a live SSO session renders a password-only form. It is the
    # intended page: no redirect, no fallback, and earlier restart attempts are cleared.
    got = run_script(
        HARNESS
        + "loadPage(); loadPage();\n"
        + "const page = loadPage({ reauth: true });\n"
        + "console.log(JSON.stringify({ page, cleared: !store.has(key) }));\n"
    )[0]
    assert got["page"]["navigations"] == []
    assert got["page"]["fallback"]["hidden"] is True
    assert got["cleared"] is True

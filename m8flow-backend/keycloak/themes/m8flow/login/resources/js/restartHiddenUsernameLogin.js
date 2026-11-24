// Only the username-only (identity-first) page is a stuck challenge. A password
// form with a hidden username is a real re-authentication and is shown as-is.
const LOGIN_RESTART_MARKER_ID = 'm8f-username-only-login';
const RESTART_GUARD_STORAGE_KEY = 'm8flow-hidden-username-login-restart-url';
const RESTART_FALLBACK_ID = 'm8f-hidden-username-login-fallback';
const MANUAL_RESTART_LINK_ID = 'm8f-return-to-full-sign-in';
const MAX_AUTO_RESTARTS_PER_CONTEXT = 2;

// This classic script is included verbatim in the HTML after the form markup.
// Recovery must not wait for a resource download or DOMContentLoaded.
const loginRecoveryStorage = () => {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null;
  }
};

const defaultMarker = () =>
  typeof document === 'undefined' ? null : document.getElementById(LOGIN_RESTART_MARKER_ID);

const restartUrlFromMarker = (marker, currentHref) => {
  if (!marker || typeof marker.getAttribute !== 'function') {
    return null;
  }

  const restartUrl = marker.getAttribute('data-login-restart-url');
  if (typeof restartUrl !== 'string') {
    return null;
  }

  return safeHttpUrl(restartUrl.trim(), currentHref);
};

// Restart targets we follow: same-origin only -- a path, or an absolute http(s) URL on
// the login page's own origin (Keycloak renders url.loginRestartFlowUrl on that origin).
// Anything else returns null, so the page shows its fallback and the manual link keeps
// its server-rendered href: a refused URL never traps the user. Never javascript:/data:;
// the result is always a root path rebuilt behind a constant "/" (CodeQL js/xss-through-dom),
// so attribute text can neither become script nor name another host ("//evil").
const SAME_ORIGIN_PROBE = 'http://same-origin.invalid';

// The text between URL delimiters is decoded and re-encoded with encodeURIComponent
// (CodeQL's recognised sanitiser for DOM text reaching a URL sink). The delimiters are
// re-joined as constants, so structure such as "#/route?a=1" or "a+b" is kept exactly.
// Splitting happens on the raw text BEFORE decoding, so an encoded delimiter ("%2F",
// "%3F", "%26", ...) is decoded inside its token and re-encoded: it never becomes structure.
// A malformed escape ("%zz") throws, the URL is refused, and callers show the fallback.
const URL_DELIMITERS = ['/', '?', '&', '=', ':', '@', ',', ';', '+', '$'];

const encodeKeepingDelimiters = (text, depth = 0) =>
  depth === URL_DELIMITERS.length
    ? encodeURIComponent(decodeURIComponent(text))
    : text
        .split(URL_DELIMITERS[depth])
        .map((part) => encodeKeepingDelimiters(part, depth + 1))
        .join(URL_DELIMITERS[depth]);

const rootPath = (url) => {
  try {
    const path = encodeKeepingDelimiters(url.pathname.replace(/^\/+/, ''));
    const query = url.search.length > 1 ? `?${encodeKeepingDelimiters(url.search.slice(1))}` : '';
    const hash = url.hash.length > 1 ? `#${encodeKeepingDelimiters(url.hash.slice(1))}` : '';
    return `/${path}${query}${hash}`;
  } catch {
    return null;
  }
};

const safeHttpUrl = (
  rawUrl,
  currentHref = typeof window !== 'undefined' ? window.location?.href : undefined,
) => {
  if (!rawUrl) {
    return null;
  }

  // Relative (path-only or "restart?x") targets stay on the current origin. Parsing
  // against a probe origin and checking the host also rejects "//evil" and "/\evil",
  // which browsers treat as a different host.
  let relative;
  try {
    relative = new URL(rawUrl, SAME_ORIGIN_PROBE);
  } catch {
    return null;
  }
  if (relative.origin === SAME_ORIGIN_PROBE && !/^[a-z][a-z0-9+.-]*:/i.test(rawUrl)) {
    if (!rawUrl.startsWith('/')) {
      // Document-relative: resolve like the browser would, then keep only the path. Without
      // a current page URL there is nothing to resolve against, so refuse.
      if (!currentHref) {
        return null;
      }
      try {
        return rootPath(new URL(rawUrl, currentHref));
      } catch {
        return null;
      }
    }
    return rootPath(relative);
  }

  let parsed;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }
  if ((parsed.protocol !== 'https:' && parsed.protocol !== 'http:') || !parsed.host) {
    return null;
  }

  // Absolute URLs must stay on the current origin; with no known origin, refuse.
  let currentOrigin;
  try {
    currentOrigin = currentHref ? new URL(currentHref).origin : null;
  } catch {
    currentOrigin = null;
  }
  if (!currentOrigin || parsed.origin !== currentOrigin) {
    return null;
  }

  // Same origin as the page, so the path alone navigates to the same place.
  return rootPath(parsed);
};

const showFallback = () => {
  const status = document.getElementById('m8f-login-recovery-status');
  if (status) {
    status.hidden = true;
  }
  const fallback = document.getElementById(RESTART_FALLBACK_ID);
  if (!fallback) {
    return;
  }

  fallback.hidden = false;
};

const restartContext = (restartUrl, currentHref) => {
  const current = new URL(currentHref);
  const target = new URL(restartUrl, current);
  // session_code, execution and client_data can change on every response.
  // Count those responses together within the same realm/client/login tab.
  return JSON.stringify([
    target.origin,
    target.pathname.split('/login-actions/')[0],
    target.searchParams.get('client_id') || current.searchParams.get('client_id') || '',
    target.searchParams.get('tab_id') || current.searchParams.get('tab_id') || '',
  ]);
};

const parseRestartGuard = (rawValue) => {
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (
      (typeof parsed?.context === 'string' || typeof parsed?.restartUrl === 'string') &&
      Number.isInteger(parsed?.attempts) &&
      parsed.attempts >= 0
    ) {
      return parsed;
    }
  } catch {
    if (typeof rawValue === 'string' && rawValue.trim()) {
      return { restartUrl: rawValue.trim(), attempts: MAX_AUTO_RESTARTS_PER_CONTEXT };
    }
  }

  return null;
};

const clearRestartGuard = (storage) => {
  try {
    storage?.removeItem(RESTART_GUARD_STORAGE_KEY);
  } catch {
    // The server-rendered manual link remains usable without browser storage.
  }
};

const manualRestartLink = () => {
  if (typeof document === 'undefined') {
    return null;
  }

  return document.getElementById(MANUAL_RESTART_LINK_ID);
};

const handleManualHiddenUsernameRestart = (
  button = manualRestartLink(),
  locationObject = typeof window !== 'undefined' ? window.location : null,
  storage = loginRecoveryStorage(),
) => {
  if (!button) {
    return false;
  }

  const restartUrl = restartUrlFromMarker(button, locationObject?.href);
  if (!restartUrl || !locationObject || typeof locationObject.replace !== 'function') {
    return false;
  }

  clearRestartGuard(storage);
  try {
    locationObject.replace(restartUrl);
    return true;
  } catch {
    return false;
  }
};

const wireManualHiddenUsernameRestart = (
  button = manualRestartLink(),
  locationObject = typeof window !== 'undefined' ? window.location : null,
  storage = loginRecoveryStorage(),
) => {
  if (!button || typeof button.addEventListener !== 'function') {
    return;
  }

  button.addEventListener('click', (event) => {
    if (handleManualHiddenUsernameRestart(button, locationObject, storage)) {
      event.preventDefault();
    }
  });
};

const restartHiddenUsernameLogin = (
  marker = defaultMarker(),
  locationObject = typeof window !== 'undefined' ? window.location : null,
  storage = loginRecoveryStorage(),
) => {
  if (!marker) {
    // Any password form (combined or re-auth) is a usable page: reset the counter.
    if (document.getElementById('password')) {
      clearRestartGuard(storage);
    }
    return false;
  }

  const restartUrl = restartUrlFromMarker(marker, locationObject?.href);
  if (!restartUrl || !locationObject || typeof locationObject.replace !== 'function' || !storage) {
    showFallback();
    return false;
  }

  try {
    const context = restartContext(restartUrl, locationObject.href);
    const currentGuard = parseRestartGuard(storage.getItem(RESTART_GUARD_STORAGE_KEY));
    const previousContext = currentGuard?.context || (
      currentGuard?.restartUrl ? restartContext(currentGuard.restartUrl, locationObject.href) : null
    );
    const attempts = previousContext === context ? currentGuard.attempts : 0;
    if (attempts >= MAX_AUTO_RESTARTS_PER_CONTEXT) {
      showFallback();
      return false;
    }

    storage.setItem(
      RESTART_GUARD_STORAGE_KEY,
      JSON.stringify({ context, attempts: attempts + 1 }),
    );
    locationObject.replace(restartUrl);
    return true;
  } catch {
    // Fail visibly rather than loop when storage is blocked or navigation fails.
    showFallback();
    return false;
  }
};

if (typeof window !== 'undefined') {
  wireManualHiddenUsernameRestart();
  restartHiddenUsernameLogin();
}

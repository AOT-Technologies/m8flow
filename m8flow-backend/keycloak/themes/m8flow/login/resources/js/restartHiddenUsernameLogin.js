const LOGIN_RESTART_MARKER_IDS = [
  'm8f-hidden-username-login',
  'm8f-username-only-login',
];
const RESTART_GUARD_STORAGE_KEY = 'm8flow-hidden-username-login-restart-url';
const RESTART_FALLBACK_ID = 'm8f-hidden-username-login-fallback';
const MANUAL_RESTART_LINK_ID = 'm8f-return-to-full-sign-in';
const MAX_AUTO_RESTARTS_PER_URL = 2;

const defaultMarker = () => {
  if (typeof document === 'undefined') {
    return null;
  }

  for (const markerId of LOGIN_RESTART_MARKER_IDS) {
    const marker = document.getElementById(markerId);
    if (marker) {
      return marker;
    }
  }

  return null;
};

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

export const safeHttpUrl = (
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

const fallbackElement = (marker) => {
  if (!marker || typeof document === 'undefined') {
    return null;
  }

  const fallbackId =
    marker.getAttribute?.('data-login-restart-fallback-id') || RESTART_FALLBACK_ID;
  if (typeof fallbackId !== 'string' || !fallbackId.trim()) {
    return null;
  }

  return document.getElementById(fallbackId.trim());
};

const showFallback = (marker) => {
  const fallback = fallbackElement(marker);
  if (!fallback) {
    return;
  }

  fallback.hidden = false;
};

const parseRestartGuard = (rawValue) => {
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (
      typeof parsed?.restartUrl === 'string' &&
      parsed.restartUrl &&
      Number.isInteger(parsed?.attempts) &&
      parsed.attempts >= 0
    ) {
      return parsed;
    }
  } catch {
    if (typeof rawValue === 'string' && rawValue.trim()) {
      return { restartUrl: rawValue.trim(), attempts: MAX_AUTO_RESTARTS_PER_URL };
    }
  }

  return null;
};

const clearRestartGuard = (storage) => {
  storage?.removeItem(RESTART_GUARD_STORAGE_KEY);
};

const manualRestartLink = () => {
  if (typeof document === 'undefined') {
    return null;
  }

  return document.getElementById(MANUAL_RESTART_LINK_ID);
};

export const handleManualHiddenUsernameRestart = (
  button = manualRestartLink(),
  locationObject = typeof window !== 'undefined' ? window.location : null,
  storage = typeof window !== 'undefined' ? window.sessionStorage : null,
) => {
  if (!button) {
    return false;
  }

  const restartUrl = restartUrlFromMarker(button, locationObject?.href);
  if (!restartUrl || !locationObject || typeof locationObject.replace !== 'function') {
    return false;
  }

  clearRestartGuard(storage);
  locationObject.replace(restartUrl);
  return true;
};

const wireManualHiddenUsernameRestart = (
  button = manualRestartLink(),
  locationObject = typeof window !== 'undefined' ? window.location : null,
  storage = typeof window !== 'undefined' ? window.sessionStorage : null,
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

export const restartHiddenUsernameLogin = (
  marker = defaultMarker(),
  locationObject = typeof window !== 'undefined' ? window.location : null,
  storage = typeof window !== 'undefined' ? window.sessionStorage : null,
) => {
  if (!marker) {
    clearRestartGuard(storage);
    return false;
  }

  const restartUrl = restartUrlFromMarker(marker, locationObject?.href);
  if (!restartUrl || !locationObject || typeof locationObject.replace !== 'function' || !storage) {
    showFallback(marker);
    return false;
  }

  const currentGuard = parseRestartGuard(storage.getItem(RESTART_GUARD_STORAGE_KEY));
  const attemptsForUrl =
    currentGuard?.restartUrl === restartUrl ? currentGuard.attempts : 0;
  if (attemptsForUrl >= MAX_AUTO_RESTARTS_PER_URL) {
    showFallback(marker);
    return false;
  }

  storage.setItem(
    RESTART_GUARD_STORAGE_KEY,
    JSON.stringify({
      restartUrl,
      attempts: attemptsForUrl + 1,
    }),
  );
  locationObject.replace(restartUrl);
  return true;
};

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      () => {
        wireManualHiddenUsernameRestart();
        restartHiddenUsernameLogin();
      },
      {
        once: true,
      },
    );
  } else {
    wireManualHiddenUsernameRestart();
    restartHiddenUsernameLogin();
  }
}

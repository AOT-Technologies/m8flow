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

const restartUrlFromMarker = (marker) => {
  if (!marker || typeof marker.getAttribute !== 'function') {
    return null;
  }

  const restartUrl = marker.getAttribute('data-login-restart-url');
  if (typeof restartUrl !== 'string') {
    return null;
  }

  const normalizedRestartUrl = restartUrl.trim();
  return normalizedRestartUrl || null;
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

  const restartUrl = restartUrlFromMarker(button);
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

  const restartUrl = restartUrlFromMarker(marker);
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

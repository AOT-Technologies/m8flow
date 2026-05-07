const LOGIN_RESTART_MARKER_IDS = [
  'm8f-hidden-username-login',
  'm8f-username-only-login',
];
const RESTART_GUARD_STORAGE_KEY = 'm8flow-hidden-username-login-restart-url';

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

export const restartHiddenUsernameLogin = (
  marker = defaultMarker(),
  locationObject = typeof window !== 'undefined' ? window.location : null,
  storage = typeof window !== 'undefined' ? window.sessionStorage : null,
) => {
  if (!marker) {
    storage?.removeItem(RESTART_GUARD_STORAGE_KEY);
    return false;
  }

  const restartUrl = restartUrlFromMarker(marker);
  if (!restartUrl || !locationObject || typeof locationObject.replace !== 'function' || !storage) {
    return false;
  }

  if (storage.getItem(RESTART_GUARD_STORAGE_KEY) === restartUrl) {
    return false;
  }

  storage.setItem(RESTART_GUARD_STORAGE_KEY, restartUrl);
  locationObject.replace(restartUrl);
  return true;
};

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => restartHiddenUsernameLogin(), {
      once: true,
    });
  } else {
    restartHiddenUsernameLogin();
  }
}

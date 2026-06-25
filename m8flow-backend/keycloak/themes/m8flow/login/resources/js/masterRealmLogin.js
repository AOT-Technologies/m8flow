const DEFAULT_MASTER_REALM_IDENTIFIER = 'master';
const DEFAULT_PLATFORM_ADMIN_PATH = '/tenants';

const extractStateValue = (rawState, key) => {
  if (!rawState) {
    return null;
  }

  const stateMatcher = new RegExp(`['"]${key}['"]\\s*:\\s*['"]([^'"]+)['"]`);
  const match = rawState.match(stateMatcher);
  return match?.[1] || null;
};

const decodeStatePayload = (state) => {
  if (!state) {
    return null;
  }

  try {
    return window.atob(decodeURIComponent(state));
  } catch {
    return null;
  }
};

const decodeBase64Url = (value) => {
  if (!value) {
    return null;
  }

  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    return window.atob(padded);
  } catch {
    return null;
  }
};

const parseClientData = (currentUrl) => {
  const decoded = decodeBase64Url(currentUrl.searchParams.get('client_data'));
  if (!decoded) {
    return null;
  }

  try {
    return JSON.parse(decoded);
  } catch {
    return null;
  }
};

export const extractBackendBaseUrl = (currentLocationHref) => {
  try {
    const currentUrl = new URL(currentLocationHref);
    const redirectUri =
      currentUrl.searchParams.get('redirect_uri') || parseClientData(currentUrl)?.ru;
    if (!redirectUri) {
      return null;
    }

    const parsedRedirectUri = new URL(redirectUri, currentUrl.origin);
    const normalizedPath = parsedRedirectUri.pathname.replace(/\/login_return\/?$/, '');
    return `${parsedRedirectUri.origin}${normalizedPath}`;
  } catch {
    return null;
  }
};

export const extractFrontendOrigin = (currentLocationHref, referrer = '') => {
  try {
    const currentUrl = new URL(currentLocationHref);
    const stateParam =
      currentUrl.searchParams.get('state') || parseClientData(currentUrl)?.st;
    const decodedState = decodeStatePayload(stateParam);
    const finalUrl = extractStateValue(decodedState, 'final_url');
    if (finalUrl) {
      return new URL(finalUrl).origin;
    }
  } catch {
    // Ignore malformed state and fall back to referrer parsing below.
  }

  if (!referrer) {
    return null;
  }

  try {
    const referrerUrl = new URL(referrer);
    const redirectUrl = referrerUrl.searchParams.get('redirect_url');
    if (!redirectUrl) {
      return null;
    }
    return new URL(redirectUrl, referrerUrl.origin).origin;
  } catch {
    return null;
  }
};

export const buildMasterRealmLoginUrl = (
  currentLocationHref,
  referrer = '',
  {
    masterRealmIdentifier = DEFAULT_MASTER_REALM_IDENTIFIER,
    platformAdminPath = DEFAULT_PLATFORM_ADMIN_PATH,
  } = {},
) => {
  const backendBaseUrl = extractBackendBaseUrl(currentLocationHref);
  const frontendOrigin = extractFrontendOrigin(currentLocationHref, referrer);
  if (!backendBaseUrl || !frontendOrigin) {
    return null;
  }

  const redirectTarget = new URL(platformAdminPath, `${frontendOrigin}/`).toString();
  const loginUrl = new URL(`${backendBaseUrl.replace(/\/$/, '')}/login`);
  loginUrl.searchParams.set('redirect_url', redirectTarget);
  loginUrl.searchParams.set('authentication_identifier', masterRealmIdentifier);
  return loginUrl.toString();
};

export const wireMasterRealmLoginButton = (button = document.getElementById('m8f-master-login-button')) => {
  if (!button) {
    return;
  }

  const loginUrl = buildMasterRealmLoginUrl(window.location.href, document.referrer, {
    masterRealmIdentifier:
      button.getAttribute('data-master-realm') || DEFAULT_MASTER_REALM_IDENTIFIER,
    platformAdminPath:
      button.getAttribute('data-platform-admin-path') || DEFAULT_PLATFORM_ADMIN_PATH,
  });

  if (!loginUrl) {
    return;
  }

  button.setAttribute('href', loginUrl);
  button.removeAttribute('aria-disabled');
};

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => wireMasterRealmLoginButton(), {
      once: true,
    });
  } else {
    wireMasterRealmLoginButton();
  }

  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      wireMasterRealmLoginButton();
    }
  });
}

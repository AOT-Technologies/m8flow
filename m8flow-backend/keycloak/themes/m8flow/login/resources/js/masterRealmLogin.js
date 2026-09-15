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
    // The established frontend flow encodes `final_url`; the repo-owned
    // browser login controller encodes `redirect_url`. Supporting both keeps
    // the platform-admin link enabled for either entry point.
    const appUrl =
      extractStateValue(decodedState, 'final_url') ||
      extractStateValue(decodedState, 'redirect_url');
    if (appUrl) {
      return new URL(appUrl).origin;
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
  // Always force credentials when switching to master from the shared login
  // page — otherwise a leftover master SSO session silently signs the user in
  // after they only logged out of the shared realm.
  loginUrl.searchParams.set('prompt', 'login');
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

// The shared login theme renders one of these per page: the "platform admin
// sign in" link (m8flow realm -> master) or the "back to sign in" link
// (master realm -> m8flow). Wiring by data attribute rather than a fixed id
// lets both reuse the same button-building logic.
const wireAllMasterRealmLoginButtons = () => {
  document
    .querySelectorAll('[data-master-realm-login-button]')
    .forEach((button) => wireMasterRealmLoginButton(button));
};

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => wireAllMasterRealmLoginButtons(), {
      once: true,
    });
  } else {
    wireAllMasterRealmLoginButtons();
  }

  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      wireAllMasterRealmLoginButtons();
    }
  });
}

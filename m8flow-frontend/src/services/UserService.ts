import { jwtDecode } from 'jwt-decode';
import * as cookie from 'cookie';
import { BACKEND_BASE_URL } from '@spiffworkflow-frontend/config';
import { AuthenticationOption } from '@spiffworkflow-frontend/interfaces';
import { parseTaskShowUrl } from '@spiffworkflow-frontend/helpers';
import {
  getEnableMultitenant,
  getMasterRealmIdentifier,
  getSharedRealmIdentifier,
} from '../utils/useConfig';

// NOTE: this currently stores the jwt token in local storage
// which is considered insecure. Server set cookies seem to be considered
// the most secure but they require both frontend and backend to be on the same
// domain which we probably can't guarantee. We could also use cookies directly
// but they have the same XSS issues as local storage.
//
// Some explanation:
// https://dev.to/nilanth/how-to-secure-jwt-in-a-single-page-application-cko

const SIGN_IN_PATH = '/';
const AUTH_REALM_HINT_STORAGE_KEY = 'm8flow_auth_realm';
const TENANT_DISPLAY_NAME_OVERRIDES_STORAGE_KEY = 'm8flow_tenant_display_names';
const TENANT_DISPLAY_NAME_UPDATED_EVENT = 'm8flow:tenant-display-name-updated';
const DEFAULT_SHARED_REALM_IDENTIFIER = 'm8flow';
const DEFAULT_SHARED_REALM_LABEL = 'M8Flow Realm';

export interface OrganizationMembership {
  alias: string;
  id: string | null;
  name: string | null;
}

interface TenantDisplayNameReference {
  alias?: string | null;
  id?: string | null;
  name?: string | null;
}

const normalizeTenantIdentifier = (value: string | null | undefined): string | null => {
  if (typeof value !== 'string') {
    return null;
  }

  const normalizedValue = value.trim();
  return normalizedValue || null;
};

const readTenantDisplayNameOverrides = (): Record<string, string> => {
  const storedValue = localStorage.getItem(TENANT_DISPLAY_NAME_OVERRIDES_STORAGE_KEY);
  if (!storedValue) {
    return {};
  }

  try {
    const parsedValue = JSON.parse(storedValue) as unknown;
    if (!parsedValue || typeof parsedValue !== 'object' || Array.isArray(parsedValue)) {
      return {};
    }

    return Object.entries(parsedValue as Record<string, unknown>).reduce<Record<string, string>>(
      (accumulator, [identifier, name]) => {
        const normalizedIdentifier = normalizeTenantIdentifier(identifier);
        const normalizedName = normalizeTenantIdentifier(
          typeof name === 'string' ? name : null,
        );
        if (normalizedIdentifier && normalizedName) {
          accumulator[normalizedIdentifier] = normalizedName;
        }
        return accumulator;
      },
      {},
    );
  } catch {
    return {};
  }
};

const writeTenantDisplayNameOverrides = (overrides: Record<string, string>) => {
  const overrideEntries = Object.entries(overrides);
  if (!overrideEntries.length) {
    localStorage.removeItem(TENANT_DISPLAY_NAME_OVERRIDES_STORAGE_KEY);
    return;
  }

  localStorage.setItem(
    TENANT_DISPLAY_NAME_OVERRIDES_STORAGE_KEY,
    JSON.stringify(Object.fromEntries(overrideEntries)),
  );
};

const getRememberedTenantDisplayName = (
  tenantIdentifiers: Array<string | null | undefined>,
): string | null => {
  const overrides = readTenantDisplayNameOverrides();
  for (const tenantIdentifier of tenantIdentifiers) {
    const normalizedIdentifier = normalizeTenantIdentifier(tenantIdentifier);
    if (!normalizedIdentifier) {
      continue;
    }
    const rememberedName = normalizeTenantIdentifier(overrides[normalizedIdentifier]);
    if (rememberedName) {
      return rememberedName;
    }
  }
  return null;
};

const dispatchTenantDisplayNameUpdated = (detail: TenantDisplayNameReference) => {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(
    new CustomEvent(TENANT_DISPLAY_NAME_UPDATED_EVENT, {
      detail,
    }),
  );
};

const rememberTenantDisplayName = (tenant: TenantDisplayNameReference) => {
  const normalizedName = normalizeTenantIdentifier(tenant.name);
  if (!normalizedName) {
    return;
  }

  const identifiers = [
    normalizeTenantIdentifier(tenant.id),
    normalizeTenantIdentifier(tenant.alias),
  ].filter((value): value is string => Boolean(value));

  if (!identifiers.length) {
    return;
  }

  const overrides = readTenantDisplayNameOverrides();
  identifiers.forEach((identifier) => {
    overrides[identifier] = normalizedName;
  });
  writeTenantDisplayNameOverrides(overrides);
  dispatchTenantDisplayNameUpdated({
    id: normalizeTenantIdentifier(tenant.id),
    alias: normalizeTenantIdentifier(tenant.alias),
    name: normalizedName,
  });
};

const getCookie = (key: string) => {
  const parsedCookies = cookie.parse(document.cookie);
  if (key in parsedCookies) {
    return parsedCookies[key];
  }
  return null;
};

const getCurrentLocation = (queryParams: string = globalThis.location.search) => {
  let queryParamString = '';
  if (queryParams) {
    queryParamString = `${queryParams}`;
  }
  return encodeURIComponent(
    `${globalThis.location.origin}${globalThis.location.pathname}${queryParamString}`,
  );
};

const getCurrentLocationRaw = (queryParams: string = globalThis.location.search) => {
  let queryParamString = '';
  if (queryParams) {
    queryParamString = `${queryParams}`;
  }
  return `${globalThis.location.origin}${globalThis.location.pathname}${queryParamString}`;
};

const normalizeRedirectUrl = (redirectUrl?: string | null) => {
  if (!redirectUrl) {
    return getCurrentLocationRaw();
  }
  return new URL(redirectUrl, globalThis.location.origin).toString();
};

const getCurrentLoginLandingUrl = () =>
  `${globalThis.location.origin}${globalThis.location.pathname}${globalThis.location.search || ''}`.replace(
    /\/login.*$/,
    '/login',
  ) || `${globalThis.location.origin}/login`;

const getAuthenticationLabel = (
  identifier: string,
  sharedRealmIdentifier: string,
  masterRealmIdentifier: string,
) => {
  if (identifier === masterRealmIdentifier) {
    return 'Master';
  }
  if (identifier === sharedRealmIdentifier) {
    return sharedRealmIdentifier === DEFAULT_SHARED_REALM_IDENTIFIER
      ? DEFAULT_SHARED_REALM_LABEL
      : sharedRealmIdentifier;
  }
  return identifier || 'Default';
};

const originalUrlTargetsOrganizationManagement = (originalUrl: string | null) => {
  if (!originalUrl) {
    return false;
  }

  try {
    const pathname =
      new URL(originalUrl, globalThis.location.origin).pathname.replace(/\/+$/, '') || '/';
    return pathname === '/tenants';
  } catch {
    return false;
  }
};

const clearSelectedTenantState = () => {
  localStorage.removeItem('m8flow_tenant');
  localStorage.removeItem('m8f_tenant_id');
  document.cookie = 'm8flow_selected_tenant=; Max-Age=0; Path=/';
};

const redirectToLogin = () => {
  if (beginAutomaticReauthentication({ originalUrl: getCurrentLocationRaw() })) {
    return;
  }
  const encodedUrl = getCurrentLocation();
  const loginUrl = `/login?original_url=${encodedUrl}`;
  globalThis.location.replace(loginUrl);
};

const checkPathForTaskShowParams = (
  redirectUrl: string = globalThis.location.href,
) => {
  const pathSegments = parseTaskShowUrl(
    normalizeRedirectUrl(redirectUrl),
  );
  if (pathSegments) {
    return { process_instance_id: pathSegments[1], task_guid: pathSegments[2] };
  }
  return null;
};

// required for logging out
const getIdToken = () => {
  return getCookie('id_token');
};
const getAccessToken = () => {
  return getCookie('access_token');
};
const getAuthenticationIdentifier = () => {
  return getCookie('authentication_identifier');
};

const getSelectedTenantCookie = () => {
  return getCookie('m8flow_selected_tenant');
};

const hasSelectedTenantCookie = () => {
  return !!getSelectedTenantCookie();
};

const getAuthenticationRealmHint = () => {
  const cookieValue = getCookie(AUTH_REALM_HINT_STORAGE_KEY);
  if (cookieValue) {
    return cookieValue;
  }
  return localStorage.getItem(AUTH_REALM_HINT_STORAGE_KEY);
};

const setAuthenticationRealmHint = (identifier: string) => {
  const normalizedIdentifier = identifier.trim();
  if (!normalizedIdentifier) {
    return;
  }

  document.cookie = `${AUTH_REALM_HINT_STORAGE_KEY}=${encodeURIComponent(normalizedIdentifier)}; Path=/`;
  localStorage.setItem(AUTH_REALM_HINT_STORAGE_KEY, normalizedIdentifier);
};

const clearAuthenticationRealmHint = () => {
  document.cookie = `${AUTH_REALM_HINT_STORAGE_KEY}=; Max-Age=0; Path=/`;
  localStorage.removeItem(AUTH_REALM_HINT_STORAGE_KEY);
};

const getDecodedIdToken = (): Record<string, unknown> | null => {
  const idToken = getIdToken();
  if (!idToken) {
    return null;
  }

  try {
    return jwtDecode(idToken) as Record<string, unknown>;
  } catch {
    return null;
  }
};

const getSingleOrganizationClaim = (
  idObject: Record<string, unknown> | null,
): { alias: string; details: Record<string, unknown> } | null => {
  if (!idObject) {
    return null;
  }

  const organizationClaim = idObject.organization;
  if (!organizationClaim || typeof organizationClaim !== 'object' || Array.isArray(organizationClaim)) {
    return null;
  }

  const organizationEntries = Object.entries(organizationClaim).filter(
    ([alias, details]) => typeof alias === 'string'
      && alias.length > 0
      && details
      && typeof details === 'object'
      && !Array.isArray(details),
  ) as Array<[string, Record<string, unknown>]>;

  if (organizationEntries.length !== 1) {
    return null;
  }

  const [alias, details] = organizationEntries[0];
  return { alias, details };
};

const getOrganizationMemberships = (): OrganizationMembership[] => {
  const idObject = getDecodedIdToken();
  if (!idObject) {
    return [];
  }

  const organizationClaim = idObject.organization;
  if (Array.isArray(organizationClaim)) {
    return organizationClaim.flatMap((item) => {
      if (typeof item === 'string' && item.length > 0) {
        return [{
          alias: item,
          id: null,
          name: getRememberedTenantDisplayName([item]),
        }];
      }
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const itemRecord = item as Record<string, unknown>;
        if (typeof itemRecord.alias === 'string' && itemRecord.alias.length > 0) {
          const itemId =
            typeof itemRecord.id === 'string' && itemRecord.id ? itemRecord.id : null;
          return [{
            alias: itemRecord.alias,
            id: itemId,
            name:
              getRememberedTenantDisplayName([itemId, itemRecord.alias])
              || (
                typeof itemRecord.name === 'string' && itemRecord.name
                  ? itemRecord.name
                  : null
              ),
          }];
        }
      }
      return [];
    });
  }

  if (!organizationClaim || typeof organizationClaim !== 'object') {
    return [];
  }

  return Object.entries(organizationClaim).flatMap(([alias, details]) => {
    if (
      typeof alias !== 'string'
      || !alias.length
      || !details
      || typeof details !== 'object'
      || Array.isArray(details)
    ) {
      return [];
    }

    const organizationDetails = details as Record<string, unknown>;
    const membershipId =
      typeof organizationDetails.id === 'string' && organizationDetails.id
        ? organizationDetails.id
        : null;
    const membershipName =
      getRememberedTenantDisplayName([membershipId, alias])
      || (
        typeof organizationDetails.name === 'string' && organizationDetails.name
          ? organizationDetails.name
          : null
      );

    return [{
      alias,
      id: membershipId,
      name: membershipName,
    }];
  });
};

const getSelectedTenantMembership = (
  organizationMemberships: OrganizationMembership[],
): OrganizationMembership | null => {
  const selectedTenantId = normalizeTenantIdentifier(localStorage.getItem('m8f_tenant_id'));
  const selectedTenantAlias = normalizeTenantIdentifier(localStorage.getItem('m8flow_tenant'));

  if (!selectedTenantId && !selectedTenantAlias) {
    return null;
  }

  return organizationMemberships.find((membership) => (
    (selectedTenantId && membership.id === selectedTenantId)
    || (selectedTenantAlias && membership.alias === selectedTenantAlias)
  )) || null;
};

const tokenHasExpired = (decodedToken: Record<string, unknown> | null): boolean => {
  if (!decodedToken) {
    return false;
  }

  const expClaim = decodedToken.exp;
  const expSeconds =
    typeof expClaim === 'number'
      ? expClaim
      : typeof expClaim === 'string'
        ? Number(expClaim)
        : NaN;

  if (!Number.isFinite(expSeconds)) {
    return false;
  }

  return (expSeconds as number) * 1000 <= Date.now();
};

const isLoggedIn = () => {
  const accessToken = getAccessToken();
  if (!accessToken) {
    return false;
  }

  const decodedAccessToken = decodeTokenRecord(accessToken);
  if (!decodedAccessToken) {
    return false;
  }

  return !tokenHasExpired(decodedAccessToken);
};

const isPublicUser = () => {
  const idToken = getIdToken();
  if (idToken) {
    const idObject = jwtDecode(idToken);
    return (idObject as any).public;
  }
  return false;
};

const SUPER_ADMIN_ROLE = 'super-admin';

const groupIndicatesSuperAdmin = (group: string): boolean => {
  const normalized = group.replace(/^\/+|\/+$/g, '').split('/').pop();
  return (
    normalized === SUPER_ADMIN_ROLE ||
    (normalized?.endsWith(`:${SUPER_ADMIN_ROLE}`) ?? false)
  );
};

const tokenIndicatesSuperAdmin = (decoded: Record<string, unknown>): boolean => {
  const roles = decoded.roles;
  if (Array.isArray(roles) && roles.includes(SUPER_ADMIN_ROLE)) {
    return true;
  }

  const groups = decoded.groups;
  if (Array.isArray(groups)) {
    for (const group of groups) {
      if (typeof group === 'string' && groupIndicatesSuperAdmin(group)) {
        return true;
      }
    }
  }

  const realmAccess = decoded.realm_access;
  if (realmAccess && typeof realmAccess === 'object') {
    const realmRoles = (realmAccess as Record<string, unknown>).roles;
    if (Array.isArray(realmRoles) && realmRoles.includes(SUPER_ADMIN_ROLE)) {
      return true;
    }
  }

  return false;
};

const decodeTokenRecord = (
  token: string | null | undefined,
): Record<string, unknown> | null => {
  if (!token) {
    return null;
  }
  try {
    return jwtDecode(token) as Record<string, unknown>;
  } catch {
    return null;
  }
};

const isSuperAdmin = (): boolean => {
  // Prefer access_token: Keycloak puts M8Flow roles in a top-level `roles` claim there.
  for (const token of [getAccessToken(), getIdToken()]) {
    const decoded = decodeTokenRecord(token);
    if (decoded && tokenIndicatesSuperAdmin(decoded)) {
      return true;
    }
  }
  return false;
};

const doLogin = (
  authenticationOption?: AuthenticationOption,
  redirectUrl?: string | null,
) => {
  const normalizedRedirectUrl = normalizeRedirectUrl(redirectUrl);
  const taskShowParams = checkPathForTaskShowParams(normalizedRedirectUrl);
  const loginParams = [
    `redirect_url=${encodeURIComponent(normalizedRedirectUrl)}`,
  ];
  if (taskShowParams) {
    loginParams.push(
      `process_instance_id=${taskShowParams.process_instance_id}`,
    );
    loginParams.push(`task_guid=${taskShowParams.task_guid}`);
  }
  if (authenticationOption) {
    setAuthenticationRealmHint(authenticationOption.identifier);
    loginParams.push(
      `authentication_identifier=${authenticationOption.identifier}`,
    );
  }
  const url = `${BACKEND_BASE_URL}/login?${loginParams.join('&')}`;
  globalThis.location.href = url;
};

const beginAutomaticReauthentication = ({
  originalUrl,
  requestedAuthenticationIdentifier,
}: {
  originalUrl?: string | null;
  requestedAuthenticationIdentifier?: string | null;
} = {}): boolean => {
  try {
    const enableMultitenant = getEnableMultitenant();
    const sharedRealmIdentifier = getSharedRealmIdentifier();
    const masterRealmIdentifier = getMasterRealmIdentifier();
    const normalizedOriginalUrl =
      typeof originalUrl === 'string' && originalUrl.trim()
        ? normalizeRedirectUrl(originalUrl)
        : originalUrl || null;
    const requestedIdentifier = requestedAuthenticationIdentifier?.trim() || '';
    const persistedRealmHintIdentifier = getAuthenticationRealmHint()?.trim() || '';
    const destinationRealmIdentifier = originalUrlTargetsOrganizationManagement(
      normalizedOriginalUrl,
    )
      ? masterRealmIdentifier
      : persistedRealmHintIdentifier || sharedRealmIdentifier;
    const identifier = requestedIdentifier || destinationRealmIdentifier;

    clearSelectedTenantState();
    doLogin(
      {
        identifier,
        label: getAuthenticationLabel(
          identifier,
          sharedRealmIdentifier,
          masterRealmIdentifier,
        ),
        uri: '',
      },
      enableMultitenant
        ? normalizedOriginalUrl || getCurrentLoginLandingUrl()
        : normalizedOriginalUrl,
    );
    return true;
  } catch {
    return false;
  }
};

const doLogout = () => {
  const idToken = getIdToken();
  clearAuthenticationRealmHint();

  const frontendBaseUrl = globalThis.location.origin;
  let logoutRedirectUrl = `${BACKEND_BASE_URL}/logout?redirect_url=${frontendBaseUrl}&id_token=${idToken}&authentication_identifier=${getAuthenticationIdentifier()}`;

  // edge case. if the user is already logged out, just take them somewhere that will force them to sign in.
  if (idToken === null) {
    logoutRedirectUrl = SIGN_IN_PATH;
  } else if (isPublicUser()) {
    logoutRedirectUrl += '&backend_only=true';
  }

  globalThis.location.href = logoutRedirectUrl;
};

const getUserEmail = () => {
  const idToken = getIdToken();
  if (idToken) {
    const idObject = jwtDecode(idToken);
    return (idObject as any).email;
  }
  return null;
};

const getUserName = () => {
  const idToken = getIdToken();
  if (idToken) {
    const idObject = jwtDecode(idToken);
    return (idObject as any).username;
  }
  return null;
};

const authenticationDisabled = () => {
  const idToken = getIdToken();
  if (idToken) {
    const idObject = jwtDecode(idToken);
    return (idObject as any).authentication_disabled;
  }
  return false;
};

/**
 * Return prefered username
 * Somehow if using Google as the OpenID provider, the field `preferred_username` is not returned
 * therefore a special handling is added to cover the issue.
 * Please refer to following link, section 5.1 Standard Claims to find the details:
 * https://openid.net/specs/openid-connect-core-1_0.html
 * @returns string
 */
const getPreferredUsername = () => {
  const idToken = getIdToken();
  if (idToken) {
    const idObject = jwtDecode(idToken);

    if (idToken === undefined || idToken === 'undefined') {
      return null;
    }

    if ((idObject as any).preferred_username !== undefined) {
      return (idObject as any).preferred_username;
    }

    if ((idObject as any).name !== undefined) {
      // note: handling response if OpenID is using Google SSO as the provider
      return (idObject as any).name;
    }

    // fallback to `given_name` as the default value.
    return (idObject as any).given_name;
  }

  return null;
};

const getTenantId = (): string | null => {
  const idObject = getDecodedIdToken();
  if (idObject) {
    if (typeof idObject.m8flow_tenant_id === 'string' && idObject.m8flow_tenant_id) {
      return idObject.m8flow_tenant_id;
    }
    if (typeof idObject.m8flow_tenant_alias === 'string' && idObject.m8flow_tenant_alias) {
      return idObject.m8flow_tenant_alias;
    }

    const organization = getSingleOrganizationClaim(idObject);
    if (organization) {
      if (typeof organization.details.id === 'string' && organization.details.id) {
        return organization.details.id;
      }
      return organization.alias;
    }

    if (typeof idObject.m8flow_tenant_name === 'string' && idObject.m8flow_tenant_name) {
      return idObject.m8flow_tenant_name;
    }
    if (typeof idObject.realm_id === 'string' && idObject.realm_id) {
      return idObject.realm_id;
    }
    if (typeof idObject.realm_name === 'string' && idObject.realm_name) {
      return idObject.realm_name;
    }
    if (idObject.m8f_tenant_id !== undefined) {
      return String(idObject.m8f_tenant_id);
    }
    if (idObject.tenant_id !== undefined) {
      return String(idObject.tenant_id);
    }
  }

  const storedTenantId = localStorage.getItem('m8f_tenant_id');
  return storedTenantId;
};

const setTenantId = (tenantId: string | null): void => {
  if (tenantId) {
    localStorage.setItem('m8f_tenant_id', tenantId);
  } else {
    localStorage.removeItem('m8f_tenant_id');
  }
};

const getTenantName = (): string | null => {
  const selectedTenantId = normalizeTenantIdentifier(localStorage.getItem('m8f_tenant_id'));
  const selectedTenantAlias = normalizeTenantIdentifier(localStorage.getItem('m8flow_tenant'));
  const rememberedSelectedTenantName = getRememberedTenantDisplayName([
    selectedTenantId,
    selectedTenantAlias,
  ]);

  const idObject = getDecodedIdToken();
  if (idObject) {
    const tokenTenantId = normalizeTenantIdentifier(
      typeof idObject.m8flow_tenant_id === 'string' ? idObject.m8flow_tenant_id : null,
    );
    const tokenTenantAlias = normalizeTenantIdentifier(
      typeof idObject.m8flow_tenant_alias === 'string' ? idObject.m8flow_tenant_alias : null,
    );
    const organization = getSingleOrganizationClaim(idObject);
    const organizationId = normalizeTenantIdentifier(
      organization && typeof organization.details.id === 'string' ? organization.details.id : null,
    );
    const organizationName = normalizeTenantIdentifier(
      organization && typeof organization.details.name === 'string' ? organization.details.name : null,
    );
    const selectedTenantMembership = getSelectedTenantMembership(getOrganizationMemberships());
    const selectedTenantMembershipName = normalizeTenantIdentifier(selectedTenantMembership?.name);

    const rememberedTenantName = getRememberedTenantDisplayName([
      tokenTenantId,
      tokenTenantAlias,
      organizationId,
      organization?.alias,
      selectedTenantId,
      selectedTenantAlias,
    ]);
    if (rememberedTenantName) {
      return rememberedTenantName;
    }

    if (organizationName) {
      return organizationName;
    }
    if (selectedTenantMembershipName) {
      return selectedTenantMembershipName;
    }
    if (typeof idObject.m8flow_tenant_name === 'string' && idObject.m8flow_tenant_name) {
      return idObject.m8flow_tenant_name;
    }
  }

  return rememberedSelectedTenantName;
};

const UserService = {
  authenticationDisabled,
  beginAutomaticReauthentication,
  doLogin,
  doLogout,
  getAccessToken,
  getAuthenticationIdentifier,
  getAuthenticationRealmHint,
  getCurrentLocation,
  getPreferredUsername,
  getOrganizationMemberships,
  getSelectedTenantCookie,
  getUserEmail,
  getUserName,
  getTenantId,
  rememberTenantDisplayName,
  hasSelectedTenantCookie,
  isLoggedIn,
  isSuperAdmin,
  isPublicUser,
  redirectToLogin,
  setTenantId,
  TENANT_DISPLAY_NAME_UPDATED_EVENT,
  getTenantName,
};

export default UserService;

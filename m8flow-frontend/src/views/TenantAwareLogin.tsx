/**
 * Coordinates frontend -> backend login redirects.
 *
 * In multitenant mode, fresh tenant-user logins always start against the shared
 * realm without a preselected organization. The first login discovers shared-realm
 * organization memberships; TenantSelectPage then finalizes the single available
 * tenant automatically or asks the user to choose one.
 */
import { useEffect } from 'react';
import { Typography } from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import { useConfig } from '../utils/useConfig';
import UserService from '../services/UserService';
import { M8FLOW_TENANT_STORAGE_KEY } from './TenantSelectPage';

const DEFAULT_SHARED_REALM_IDENTIFIER = 'm8flow';
const DEFAULT_SHARED_REALM_LABEL = 'M8Flow Realm';

const getCurrentLoginLandingUrl = () =>
  `${window.location.origin}${window.location.pathname}${window.location.search || ''}`.replace(
    /\/login.*$/,
    '/login',
  ) || `${window.location.origin}/login`;

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

const clearSelectedTenantState = () => {
  localStorage.removeItem(M8FLOW_TENANT_STORAGE_KEY);
  localStorage.removeItem('m8f_tenant_id');
  document.cookie = 'm8flow_selected_tenant=; Max-Age=0; Path=/';
};

export default function TenantAwareLogin() {
  const { ENABLE_MULTITENANT, MASTER_REALM_IDENTIFIER, SHARED_REALM_IDENTIFIER } =
    useConfig();
  const [searchParams] = useSearchParams();

  const originalUrl = searchParams.get('original_url');
  const requestedAuthIdentifier = (
    searchParams.get('authentication_identifier') || ''
  ).trim();

  useEffect(() => {
    if (!ENABLE_MULTITENANT) {
      clearSelectedTenantState();

      if (UserService.isLoggedIn()) {
        globalThis.location.replace('/');
        return;
      }

      const identifier = requestedAuthIdentifier || SHARED_REALM_IDENTIFIER;
      UserService.doLogin(
        {
          identifier,
          label: getAuthenticationLabel(
            identifier,
            SHARED_REALM_IDENTIFIER,
            MASTER_REALM_IDENTIFIER,
          ),
          uri: '',
        },
        originalUrl,
      );
      return;
    }

    if (UserService.isLoggedIn()) {
      globalThis.location.replace(originalUrl || '/');
      return;
    }

    const identifier = requestedAuthIdentifier || SHARED_REALM_IDENTIFIER;
    if (identifier === SHARED_REALM_IDENTIFIER) {
      clearSelectedTenantState();
    }

    UserService.doLogin(
      {
        identifier,
        label: getAuthenticationLabel(
          identifier,
          SHARED_REALM_IDENTIFIER,
          MASTER_REALM_IDENTIFIER,
        ),
        uri: '',
      },
      originalUrl || getCurrentLoginLandingUrl(),
    );
  }, [
    ENABLE_MULTITENANT,
    MASTER_REALM_IDENTIFIER,
    SHARED_REALM_IDENTIFIER,
    requestedAuthIdentifier,
    originalUrl,
  ]);

  return (
    <div style={{ padding: 24, textAlign: 'center' }}>
      <Typography>Redirecting to sign in...</Typography>
    </div>
  );
}

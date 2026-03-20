/**
 * When ENABLE_MULTITENANT and a tenant is stored, calls the backend tenant-login-url API.
 * On success redirects to backend /login with tenant param. If the stored tenant
 * no longer exists (for example after resetting Keycloak), clear the stale tenant
 * selection and return to the tenant picker. In single-tenant mode, bypasses the
 * auth option chooser and starts the m8flow login flow directly.
 */
import { useEffect, useState } from 'react';
import { Typography } from '@mui/material';
import Login from '@spiffworkflow-frontend/views/Login';
import { useSearchParams } from 'react-router-dom';
import { useConfig } from '../utils/useConfig';
import UserService from '../services/UserService';
import { M8FLOW_TENANT_STORAGE_KEY } from './TenantSelectPage';

const getRedirectUrl = () =>
  encodeURIComponent(
    `${window.location.origin}${window.location.pathname}${window.location.search || ''}`.replace(
      /\/login.*$/,
      '/'
    ) || `${window.location.origin}/`
  );

const SINGLE_TENANT_AUTH_IDENTIFIER = 'm8flow';
const SINGLE_TENANT_AUTH_LABEL = 'M8Flow Realm';

const getAuthenticationLabel = (identifier: string) => {
  if (identifier === 'master') {
    return 'Master';
  }
  if (identifier === SINGLE_TENANT_AUTH_IDENTIFIER) {
    return SINGLE_TENANT_AUTH_LABEL;
  }
  return identifier || 'Default';
};

export default function TenantAwareLogin() {
  const { ENABLE_MULTITENANT, BACKEND_BASE_URL } = useConfig();
  const [checking, setChecking] = useState(true);
  const [searchParams] = useSearchParams();

  const storedTenant =
    typeof window !== 'undefined' ? localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY) : null;
  const originalUrl = searchParams.get('original_url');
  const requestedAuthIdentifier = (searchParams.get('authentication_identifier') || '').trim();

  useEffect(() => {
    if (!ENABLE_MULTITENANT) {
      localStorage.removeItem(M8FLOW_TENANT_STORAGE_KEY);
      localStorage.removeItem('m8f_tenant_id');

      if (UserService.isLoggedIn()) {
        globalThis.location.replace('/');
        return;
      }

      const identifier = requestedAuthIdentifier || SINGLE_TENANT_AUTH_IDENTIFIER;
      UserService.doLogin(
        {
          identifier,
          label: getAuthenticationLabel(identifier),
          uri: '',
        },
        originalUrl,
      );
      return;
    }

    if (!storedTenant?.trim()) {
      setChecking(false);
      return;
    }

    const tenant = storedTenant.trim();
    const url = `${BACKEND_BASE_URL}/m8flow/tenant-login-url?tenant=${encodeURIComponent(tenant)}`;
    fetch(url, { method: 'GET', credentials: 'include' })
      .then((res) => {
        if (res.status === 404) {
          localStorage.removeItem(M8FLOW_TENANT_STORAGE_KEY);
          localStorage.removeItem('m8f_tenant_id');
          globalThis.location.replace('/');
          return null;
        }
        if (!res.ok) {
          setChecking(false);
          return null;
        }
        return res.json();
      })
      .then((data) => {
        if (data?.login_url) {
          const redirectUrl = getRedirectUrl();
          const loginUrl = `${BACKEND_BASE_URL}/login?redirect_url=${redirectUrl}&tenant=${encodeURIComponent(tenant)}&authentication_identifier=${encodeURIComponent(tenant)}`;
          window.location.href = loginUrl;
          return;
        }
        setChecking(false);
      })
      .catch(() => setChecking(false));
  }, [ENABLE_MULTITENANT, storedTenant, BACKEND_BASE_URL, requestedAuthIdentifier, originalUrl]);

  if (!ENABLE_MULTITENANT) {
    return null;
  }

  if (checking && storedTenant?.trim()) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Typography>Redirecting to login...</Typography>
      </div>
    );
  }

  return <Login />;
}

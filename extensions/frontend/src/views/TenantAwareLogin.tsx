/**
 * When ENABLE_MULTITENANT and a tenant is stored, calls the backend tenant-login-url API.
 * On success redirects to backend /login with tenant param; on 404 shows "Tenant not found".
 * Otherwise renders the default Login view.
 */
import { useEffect, useState } from 'react';
import { Typography } from '@mui/material';
import Login from '@spiffworkflow-frontend/views/Login';
import { useConfig } from '../utils/useConfig';
import { M8FLOW_TENANT_STORAGE_KEY } from './TenantSelectPage';

const getRedirectUrl = () =>
  encodeURIComponent(
    `${window.location.origin}${window.location.pathname}${window.location.search || ''}`.replace(
      /\/login.*$/,
      '/'
    ) || `${window.location.origin}/`
  );

export default function TenantAwareLogin() {
  const { ENABLE_MULTITENANT, BACKEND_BASE_URL } = useConfig();
  const [tenantNotFound, setTenantNotFound] = useState(false);
  const [checking, setChecking] = useState(true);

  const storedTenant =
    typeof window !== 'undefined' ? localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY) : null;

  useEffect(() => {
    if (!ENABLE_MULTITENANT || !storedTenant?.trim()) {
      setChecking(false);
      return;
    }
    const tenant = storedTenant.trim();
    const url = `${BACKEND_BASE_URL}/m8flow/tenant-login-url?tenant=${encodeURIComponent(tenant)}`;
    fetch(url, { method: 'GET', credentials: 'include' })
      .then((res) => {
        if (res.status === 404) {
          setTenantNotFound(true);
          setChecking(false);
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
  }, [ENABLE_MULTITENANT, storedTenant, BACKEND_BASE_URL]);

  if (checking && ENABLE_MULTITENANT && storedTenant?.trim()) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Typography>Redirecting to login…</Typography>
      </div>
    );
  }

  if (tenantNotFound) {
    return (
      <div style={{ padding: 24, maxWidth: 400 }}>
        <Typography variant="h6" color="error">
          Tenant not found
        </Typography>
        <Typography sx={{ mt: 1 }}>
          The selected tenant does not exist in Keycloak. Please choose another tenant or contact
          your administrator.
        </Typography>
      </div>
    );
  }

  return <Login />;
}

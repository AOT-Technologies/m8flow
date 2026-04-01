/**
 * Tenant selection page. When ENABLE_MULTITENANT is true this can be the default page.
 * On submit calls tenant-login-url API; only if it succeeds is the tenant saved to localStorage
 * and the browser sent into the tenant-aware login flow. Global admins can bypass
 * tenant selection and sign in through the master realm.
 */
import { Box, Container, Typography, TextField, Button } from '@mui/material';
import { FormEvent, useState } from 'react';
import { useConfig } from '../utils/useConfig';

export const M8FLOW_TENANT_STORAGE_KEY = 'm8flow_tenant';

const getRedirectUrl = () =>
  encodeURIComponent(`${globalThis.location.origin}/`);
const GLOBAL_ADMIN_LANDING_PATH = '/tenants';
const getGlobalAdminLandingUrl = () =>
  `${globalThis.location.origin}${GLOBAL_ADMIN_LANDING_PATH}`;

export default function TenantSelectPage() {
  const { ENABLE_MULTITENANT, BACKEND_BASE_URL } = useConfig();
  const [tenantName, setTenantName] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!ENABLE_MULTITENANT) {
    globalThis.location.replace('/');
    return null;
  }

  const handleGlobalAdminSignIn = () => {
    const redirectUrl = encodeURIComponent(getGlobalAdminLandingUrl());
    globalThis.location.assign(
      `${BACKEND_BASE_URL}/login?redirect_url=${redirectUrl}&authentication_identifier=master`
    );
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = tenantName.trim();
    if (!trimmed) {
      setError('Tenant name is required');
      return;
    }
    setError('');
    setSubmitting(true);
    const url = `${BACKEND_BASE_URL}/m8flow/tenant-login-url?tenant=${encodeURIComponent(trimmed)}`;
    fetch(url, { method: 'GET', credentials: 'include' })
      .then((res) => {
        if (res.status === 404) {
          setError('Tenant not found. Please check the name or contact your administrator.');
          setSubmitting(false);
          return;
        }
        if (!res.ok) {
          setError('Unable to verify tenant. Please try again.');
          setSubmitting(false);
          return;
        }
        localStorage.setItem(M8FLOW_TENANT_STORAGE_KEY, trimmed);
        const redirectUrl = getRedirectUrl();
        const loginUrl = `${BACKEND_BASE_URL}/login?redirect_url=${redirectUrl}&tenant=${encodeURIComponent(trimmed)}&authentication_identifier=${encodeURIComponent(trimmed)}`;
        globalThis.location.assign(loginUrl);
      })
      .catch(() => {
        setError('Unable to verify tenant. Please try again.');
        setSubmitting(false);
      });
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ padding: 3 }}>
        <Typography variant="h4" component="h1" sx={{ mb: 2 }}>
          Select tenant
        </Typography>
        <form onSubmit={handleSubmit} data-testid="tenant-select-form">
          <TextField
            fullWidth
            label="Tenant name"
            value={tenantName}
            onChange={(e) => setTenantName(e.target.value)}
            error={!!error}
            helperText={error}
            autoFocus
            data-testid="tenant-name-input"
            sx={{ mb: 2 }}
          />
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Button type="submit" variant="contained" disabled={submitting} data-testid="tenant-select-submit-button">
              {submitting ? 'Saving…' : 'Continue'}
            </Button>
            <Button variant="text" onClick={handleGlobalAdminSignIn} data-testid="global-admin-sign-in-button">
              Global admin sign in
            </Button>
          </Box>
        </form>
      </Box>
    </Container>
  );
}

/**
 * Tenant selection page. When ENABLE_MULTITENANT is true this can be the default page.
 * On submit calls tenant-login-url API; only if it returns a redirect URL is the tenant
 * saved to localStorage under m8flow_tenant and the user sent to the default home.
 */
import { Box, Container, Typography, TextField, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { FormEvent, useState } from 'react';
import { useConfig } from '../utils/useConfig';
import { useTenantGate } from '../contexts/TenantGateContext';

export const M8FLOW_TENANT_STORAGE_KEY = 'm8flow_tenant';

const DEBUG_LOG = (payload: Record<string, unknown>) => {
  fetch('http://127.0.0.1:7243/ingest/603ec126-81cd-4be3-ba0d-84501c09e628', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      timestamp: Date.now(),
      sessionId: 'debug-session',
    }),
  }).catch(() => {});
};

export default function TenantSelectPage() {
  const { ENABLE_MULTITENANT, BACKEND_BASE_URL } = useConfig();
  const tenantGate = useTenantGate();
  const navigate = useNavigate();
  const [tenantName, setTenantName] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // #region agent log
  DEBUG_LOG({
    hypothesisId: 'C',
    location: 'TenantSelectPage.tsx:render',
    message: 'TenantSelectPage render',
    data: { ENABLE_MULTITENANT, hasTenantGate: !!tenantGate?.onTenantSelected },
  });
  // #endregion

  if (!ENABLE_MULTITENANT) {
    // #region agent log
    DEBUG_LOG({
      hypothesisId: 'C',
      location: 'TenantSelectPage.tsx:redirect-no-multitenant',
      message: 'Redirecting because ENABLE_MULTITENANT is false',
      data: {},
    });
    // #endregion
    navigate('/', { replace: true });
    return null;
  }

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
          return null;
        }
        if (!res.ok) {
          setError('Unable to verify tenant. Please try again.');
          setSubmitting(false);
          return null;
        }
        return res.json();
      })
      .then((data) => {
        if (!data?.login_url) {
          setSubmitting(false);
          return;
        }
        localStorage.setItem(M8FLOW_TENANT_STORAGE_KEY, trimmed);
        setSubmitting(false);
        if (tenantGate?.onTenantSelected) {
          tenantGate.onTenantSelected();
        } else {
          navigate('/', { replace: true });
        }
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
        <form onSubmit={handleSubmit}>
          <TextField
            fullWidth
            label="Tenant name"
            value={tenantName}
            onChange={(e) => setTenantName(e.target.value)}
            error={!!error}
            helperText={error}
            autoFocus
            sx={{ mb: 2 }}
          />
          <Button type="submit" variant="contained" disabled={submitting}>
            {submitting ? 'Saving…' : 'Continue'}
          </Button>
        </form>
      </Box>
    </Container>
  );
}

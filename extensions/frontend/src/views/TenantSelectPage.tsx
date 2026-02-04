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

export default function TenantSelectPage() {
  const { ENABLE_MULTITENANT, BACKEND_BASE_URL } = useConfig();
  const tenantGate = useTenantGate();
  const navigate = useNavigate();
  const [tenantName, setTenantName] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!ENABLE_MULTITENANT) {
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

/**
 * Tenant selection page. When ENABLE_MULTITENANT is true this can be the default page.
 * Stores tenant id in localStorage under key m8flow_tenant (used later e.g. for X-Tenant header).
 * Validates tenant exists via unauthenticated GET /tenants/check before redirecting to login.
 */
import { Box, Typography, TextField, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { FormEvent, useState } from 'react';
import { useConfig } from '../utils/useConfig';
import { useApi } from '../utils/useApi';

export const M8FLOW_TENANT_STORAGE_KEY = 'm8flow_tenant';

type TenantCheckResponse = { exists: boolean; tenant_id?: string };

export default function TenantSelectPage() {
  const { ENABLE_MULTITENANT } = useConfig();
  const api = useApi();
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
    const path = `/tenants/check?identifier=${encodeURIComponent(trimmed)}`;
    api.makeCallToBackend({
      path,
      successCallback: (data: TenantCheckResponse) => {
        setSubmitting(false);
        if (data.exists) {
          const tenantId = data.tenant_id ?? trimmed;
          localStorage.setItem(M8FLOW_TENANT_STORAGE_KEY, tenantId);
          navigate('/login', { replace: true });
        } else {
          setError('Tenant not found');
        }
      },
      failureCallback: (err: { message?: string }) => {
        setSubmitting(false);
        setError(err?.message ?? 'Unable to verify tenant');
      },
    });
  };

  return (
    <Box sx={{ padding: 3, maxWidth: 400 }}>
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
          {submitting ? 'Checking…' : 'Continue to login'}
        </Button>
      </form>
    </Box>
  );
}

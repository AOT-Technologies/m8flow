/**
 * Tenant selection page. When ENABLE_MULTITENANT is true this can be the default page.
 * Stores tenant name in localStorage under key m8flow_tenant (used later e.g. for X-Tenant header).
 * On submit saves to localStorage and navigates to the default home page.
 */
import { Box, Typography, TextField, Button } from '@mui/material';
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
  const { ENABLE_MULTITENANT } = useConfig();
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
    localStorage.setItem(M8FLOW_TENANT_STORAGE_KEY, trimmed);
    setSubmitting(false);
    if (tenantGate?.onTenantSelected) {
      tenantGate.onTenantSelected();
    } else {
      navigate('/', { replace: true });
    }
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
          {submitting ? 'Saving…' : 'Continue'}
        </Button>
      </form>
    </Box>
  );
}

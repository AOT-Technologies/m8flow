/**
 * Multitenant landing page and post-auth tenant finalizer.
 *
 * Tenant users first authenticate against the shared realm. After credentials are
 * accepted, M8Flow either finalizes the single available organization
 * automatically or asks the user which organization to enter.
 */
import { useEffect, useRef } from 'react';
import {
  Alert,
  Box,
  Button,
  Container,
  Stack,
  Typography,
} from '@mui/material';
import UserService, { type OrganizationMembership } from '../services/UserService';
import { useConfig } from '../utils/useConfig';

export const M8FLOW_TENANT_STORAGE_KEY = 'm8flow_tenant';

const GLOBAL_ADMIN_LANDING_PATH = '/tenants';
const TENANT_FINALIZATION_REDIRECT_EXEMPT_PATHS = new Set(['/login', '/tenant']);

const getRootRedirectUrl = () => encodeURIComponent(`${globalThis.location.origin}/`);
const getGlobalAdminLandingUrl = () =>
  `${globalThis.location.origin}${GLOBAL_ADMIN_LANDING_PATH}`;
const getCurrentAbsoluteUrl = () =>
  `${globalThis.location.origin}${globalThis.location.pathname}${globalThis.location.search || ''}`;

const getTenantFinalizationRedirectUrl = () => {
  const pathname = globalThis.location.pathname || '/';
  if (TENANT_FINALIZATION_REDIRECT_EXEMPT_PATHS.has(pathname)) {
    return `${globalThis.location.origin}/`;
  }
  return getCurrentAbsoluteUrl();
};

const clearSelectedTenantState = () => {
  localStorage.removeItem(M8FLOW_TENANT_STORAGE_KEY);
  localStorage.removeItem('m8f_tenant_id');
  document.cookie = 'm8flow_selected_tenant=; Max-Age=0; Path=/';
};

const rememberSelectedTenant = (organization: OrganizationMembership) => {
  const tenantId = organization.id || organization.alias;
  localStorage.setItem(M8FLOW_TENANT_STORAGE_KEY, organization.alias);
  localStorage.setItem('m8f_tenant_id', tenantId);
  document.cookie = `m8flow_selected_tenant=${encodeURIComponent(tenantId)}; Path=/`;
};

export default function TenantSelectPage() {
  const {
    ENABLE_MULTITENANT,
    BACKEND_BASE_URL,
    MASTER_REALM_IDENTIFIER,
    SHARED_REALM_IDENTIFIER,
  } = useConfig();
  const loggedIn = UserService.isLoggedIn();
  const organizations = UserService.getOrganizationMemberships();
  const autoFinalizeStarted = useRef(false);

  const finalizeTenantLogin = (organization: OrganizationMembership) => {
    rememberSelectedTenant(organization);
    const redirectUrl = encodeURIComponent(getTenantFinalizationRedirectUrl());
    globalThis.location.assign(
      `${BACKEND_BASE_URL}/login?redirect_url=${redirectUrl}&authentication_identifier=${encodeURIComponent(SHARED_REALM_IDENTIFIER)}&tenant=${encodeURIComponent(organization.alias)}&tenant_finalization=1`,
    );
  };

  useEffect(() => {
    if (!ENABLE_MULTITENANT) {
      globalThis.location.replace('/');
      return;
    }

    if (!loggedIn || organizations.length !== 1 || autoFinalizeStarted.current) {
      return;
    }

    autoFinalizeStarted.current = true;
    finalizeTenantLogin(organizations[0]);
  }, [ENABLE_MULTITENANT, loggedIn, organizations]);

  if (!ENABLE_MULTITENANT) {
    return null;
  }

  const handleSharedRealmSignIn = () => {
    clearSelectedTenantState();
    const redirectUrl = getRootRedirectUrl();
    globalThis.location.assign(
      `${BACKEND_BASE_URL}/login?redirect_url=${redirectUrl}&authentication_identifier=${encodeURIComponent(SHARED_REALM_IDENTIFIER)}`,
    );
  };

  const handleGlobalAdminSignIn = () => {
    clearSelectedTenantState();
    const redirectUrl = encodeURIComponent(getGlobalAdminLandingUrl());
    globalThis.location.assign(
      `${BACKEND_BASE_URL}/login?redirect_url=${redirectUrl}&authentication_identifier=${encodeURIComponent(MASTER_REALM_IDENTIFIER)}`,
    );
  };

  if (!loggedIn) {
    return (
      <Container maxWidth="sm">
        <Box sx={{ padding: 3 }}>
          <Typography variant="h4" component="h1" sx={{ mb: 2 }}>
            Sign in to m8flow
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            Sign in with your shared realm account first. If your account belongs
            to more than one tenant, you will choose the tenant after your
            credentials are accepted.
          </Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <Button
              type="button"
              variant="contained"
              onClick={handleSharedRealmSignIn}
              data-testid="shared-realm-sign-in-button"
            >
              Sign in
            </Button>
            <Button
              variant="text"
              onClick={handleGlobalAdminSignIn}
              data-testid="global-admin-sign-in-button"
            >
              Platform admin sign in
            </Button>
          </Stack>
        </Box>
      </Container>
    );
  }

  if (organizations.length === 0) {
    return (
      <Container maxWidth="sm">
        <Box sx={{ padding: 3 }}>
          <Typography variant="h4" component="h1" sx={{ mb: 2 }}>
            No tenants available
          </Typography>
          <Alert severity="warning" sx={{ mb: 3 }}>
            Your account authenticated successfully, but it is not a member of any
            tenant in the shared realm.
          </Alert>
          <Button
            variant="text"
            onClick={handleGlobalAdminSignIn}
            data-testid="global-admin-sign-in-button"
          >
            Platform admin sign in
          </Button>
        </Box>
      </Container>
    );
  }

  if (organizations.length === 1) {
    return (
      <Container maxWidth="sm">
        <Box sx={{ padding: 3 }}>
          <Typography variant="h5" component="h1" sx={{ mb: 2 }}>
            Finalizing tenant access
          </Typography>
          <Typography color="text.secondary">
            Continuing into {organizations[0].name || organizations[0].alias}...
          </Typography>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="sm">
      <Box sx={{ padding: 3 }}>
        <Typography variant="h4" component="h1" sx={{ mb: 2 }}>
          Select a Tenant
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          Your account has access to more than one tenant. Choose the tenant
          you want to enter for this session.
        </Typography>
        <Stack spacing={2}>
          {organizations.map((organization) => (
            <Button
              key={organization.alias}
              variant="outlined"
              onClick={() => finalizeTenantLogin(organization)}
              data-testid={`organization-option-${organization.alias}`}
              sx={{ justifyContent: 'space-between', textTransform: 'none' }}
            >
              <span>{organization.name || organization.alias}</span>
              <span>{organization.alias}</span>
            </Button>
          ))}
        </Stack>
      </Box>
    </Container>
  );
}

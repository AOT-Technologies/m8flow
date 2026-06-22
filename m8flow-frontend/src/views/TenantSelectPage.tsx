/**
 * Multitenant landing page and post-auth tenant finalizer.
 *
 * Tenant users first authenticate against the shared realm. After credentials are
 * accepted, M8Flow either finalizes the single available organization
 * automatically or asks the user which organization to enter.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Container,
  Stack,
  Typography,
} from '@mui/material';
import UserService, { type OrganizationMembership } from '../services/UserService';
import TenantService from '../services/TenantService';
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
  UserService.rememberTenantDisplayName({
    id: organization.id,
    alias: organization.alias,
    name: organization.name,
  });
};

const mergeOrganizationMemberships = (
  currentMemberships: OrganizationMembership[],
  resolvedMemberships: OrganizationMembership[],
): OrganizationMembership[] => {
  const resolvedMembershipLookup = new Map<string, OrganizationMembership>();
  resolvedMemberships.forEach((membership) => {
    if (membership.id) {
      resolvedMembershipLookup.set(`id:${membership.id}`, membership);
    }
    resolvedMembershipLookup.set(`alias:${membership.alias}`, membership);
  });

  return currentMemberships.map((membership) => {
    const resolvedMembership = (
      (membership.id && resolvedMembershipLookup.get(`id:${membership.id}`))
      || resolvedMembershipLookup.get(`alias:${membership.alias}`)
    );
    if (!resolvedMembership) {
      return membership;
    }

    return {
      alias: membership.alias,
      id: resolvedMembership.id || membership.id,
      name: resolvedMembership.name || membership.name,
    };
  });
};

export default function TenantSelectPage() {
  const {
    ENABLE_MULTITENANT,
    BACKEND_BASE_URL,
    MASTER_REALM_IDENTIFIER,
    SHARED_REALM_IDENTIFIER,
  } = useConfig();
  const { t } = useTranslation();
  const loggedIn = UserService.isLoggedIn();
  const tokenOrganizations = UserService.getOrganizationMemberships();
  const organizationMembershipsKey = JSON.stringify(tokenOrganizations);
  const [organizations, setOrganizations] = useState<OrganizationMembership[]>(
    () => tokenOrganizations,
  );
  const autoFinalizeStarted = useRef(false);

  useEffect(() => {
    setOrganizations(tokenOrganizations);
  }, [organizationMembershipsKey]);

  useEffect(() => {
    let ignore = false;

    if (!loggedIn || tokenOrganizations.length === 0) {
      return () => {
        ignore = true;
      };
    }

    const hasMissingNames = tokenOrganizations.some((organization) => !organization.name?.trim());
    if (!hasMissingNames) {
      setOrganizations(tokenOrganizations);
      return () => {
        ignore = true;
      };
    }

    TenantService.getCurrentUserOrganizationMemberships()
      .then((resolvedOrganizations) => {
        if (ignore) {
          return;
        }

        const mergedOrganizations = mergeOrganizationMemberships(
          tokenOrganizations,
          resolvedOrganizations,
        );
        mergedOrganizations.forEach((organization) => {
          UserService.rememberTenantDisplayName(organization);
        });
        setOrganizations(mergedOrganizations);
      })
      .catch(() => {
        if (!ignore) {
          setOrganizations(tokenOrganizations);
        }
      });

    return () => {
      ignore = true;
    };
  }, [loggedIn, organizationMembershipsKey]);

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
            {t("sign_in_to_m8flow")}
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            {t("shared_realm_sign_in_description")}
          </Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <Button
              type="button"
              variant="contained"
              onClick={handleSharedRealmSignIn}
              data-testid="shared-realm-sign-in-button"
            >
              {t("sign_in")}
            </Button>
            <Button
              variant="text"
              onClick={handleGlobalAdminSignIn}
              data-testid="global-admin-sign-in-button"
            >
              {t("platform_admin_sign_in")}
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
            {t("no_tenants_available")}
          </Typography>
          <Alert severity="warning" sx={{ mb: 3 }}>
            {t("account_not_member_of_any_tenant")}
          </Alert>
          <Button
            variant="text"
            onClick={handleGlobalAdminSignIn}
            data-testid="global-admin-sign-in-button"
          >
            {t("platform_admin_sign_in")}
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
            {t("finalizing_tenant_access")}
          </Typography>
          <Typography color="text.secondary">
            {t("continuing_into_tenant", {
              tenant: organizations[0].name || organizations[0].alias,
            })}
          </Typography>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="sm">
      <Box sx={{ padding: 3 }}>
        <Typography variant="h4" component="h1" sx={{ mb: 2 }}>
          {t("select_a_tenant")}
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          {t("multi_tenant_choose_description")}
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

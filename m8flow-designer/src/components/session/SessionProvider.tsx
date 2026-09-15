import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { fetchCapabilities, fetchOrganizationMemberships, fetchTenants, type TenantSummary } from '@/lib/api';
import {
  getActiveTenantDisplayLabel,
  getSelectedTenantId,
  isSuperAdmin,
  type OrganizationMembership,
} from '@/lib/auth';
import { persistTenantId, readPersistedTenantId } from '@/lib/selectedTenant';
import { SessionContext, type SessionContextValue } from './SessionContext';

/**
 * Single source of session truth: capabilities, the tenant registry, and the
 * active-tenant rule. One bootstrap (three fetches + the cookie) fanned out
 * through the `useActiveTenant` / `useCapabilities` / `useTenantRegistry`
 * hooks — the extraction of what AppShell's outlet context used to carry.
 *
 * Mounted above AppShell (`<SessionProvider><AppShell/></SessionProvider>`) so
 * AppShell and every routed page can read the hooks.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const superAdmin = isSuperAdmin();

  const [selectedTenantId, setSelectedTenantIdState] = useState<string | null>(
    () => readPersistedTenantId(),
  );

  const [canManageProcesses, setCanManageProcesses] = useState(false);
  const [canReadSecrets, setCanReadSecrets] = useState(false);
  const [canManageSecrets, setCanManageSecrets] = useState(false);
  const [canReadConnectors, setCanReadConnectors] = useState(false);
  const [canManageConnectorProfiles, setCanManageConnectorProfiles] = useState(false);
  const [canManageTenant, setCanManageTenant] = useState(false);

  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [tenantsReloadKey, setTenantsReloadKey] = useState(0);
  const [organizationMemberships, setOrganizationMemberships] = useState<OrganizationMembership[]>([]);
  const [activeTenantLabel, setActiveTenantLabel] = useState<string | null>(() =>
    superAdmin ? null : getActiveTenantDisplayLabel(),
  );

  useEffect(() => {
    let cancelled = false;
    fetchCapabilities()
      .then((caps) => {
        if (!cancelled) {
          setCanManageProcesses(Boolean(caps.can_manage_processes));
          setCanReadSecrets(Boolean(caps.can_read_secrets));
          setCanManageSecrets(Boolean(caps.can_manage_secrets));
          setCanReadConnectors(Boolean(caps.can_read_connectors));
          setCanManageConnectorProfiles(Boolean(caps.can_manage_connector_profiles));
          setCanManageTenant(Boolean(caps.can_manage_tenant));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCanManageProcesses(false);
          setCanReadSecrets(false);
          setCanManageSecrets(false);
          setCanReadConnectors(false);
          setCanManageConnectorProfiles(false);
          setCanManageTenant(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!superAdmin) {
      return;
    }
    let cancelled = false;
    fetchTenants()
      .then((rows) => {
        if (!cancelled) {
          setTenants(rows.map((row) => ({ id: row.id, name: row.name || row.id })));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTenants([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [superAdmin, tenantsReloadKey]);

  useEffect(() => {
    if (superAdmin) {
      setActiveTenantLabel(null);
      setOrganizationMemberships([]);
      return;
    }
    setActiveTenantLabel(getActiveTenantDisplayLabel());
    let cancelled = false;
    fetchOrganizationMemberships()
      .then((rows) => {
        if (!cancelled) {
          setActiveTenantLabel(getActiveTenantDisplayLabel(rows));
          setOrganizationMemberships(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setActiveTenantLabel(getActiveTenantDisplayLabel());
        }
      });
    return () => {
      cancelled = true;
    };
  }, [superAdmin]);

  const setSelectedTenant = useCallback((tenantId: string | null) => {
    persistTenantId(tenantId);
    setSelectedTenantIdState(tenantId);
  }, []);

  const refreshTenants = useCallback(() => setTenantsReloadKey((key) => key + 1), []);

  const scopedTenantId = superAdmin ? selectedTenantId : null;

  const value = useMemo<SessionContextValue>(
    () => ({
      activeTenant: {
        activeTenantId: getSelectedTenantId(),
        selectedTenantId,
        scopedTenantId,
        isSuperAdmin: superAdmin,
        needsTenant: superAdmin && !scopedTenantId,
        setSelectedTenant,
      },
      capabilities: {
        canManageProcesses,
        canReadSecrets,
        canManageSecrets,
        canReadConnectors,
        canManageConnectorProfiles,
        canManageTenant,
      },
      registry: {
        tenants,
        refreshTenants,
        organizationMemberships,
        activeTenantLabel,
      },
    }),
    [
      selectedTenantId,
      scopedTenantId,
      superAdmin,
      setSelectedTenant,
      canManageProcesses,
      canReadSecrets,
      canManageSecrets,
      canReadConnectors,
      canManageConnectorProfiles,
      canManageTenant,
      tenants,
      refreshTenants,
      organizationMemberships,
      activeTenantLabel,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

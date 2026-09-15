import { createContext } from 'react';

import type { TenantSummary } from '@/lib/api';
import type { OrganizationMembership } from '@/lib/auth';

/**
 * The active-tenant rule, owned in one place. Two tenant notions live here and
 * are named separately on purpose (see .scratch/use-active-tenant-seam):
 * `activeTenantId` is the backend-authoritative cookie (finalization);
 * `scopedTenantId`/`selectedTenantId` are the super-admin sidebar view filter
 * (localStorage). localStorage can never open the cookie gate — keeping the
 * two named apart is what structurally protects that invariant.
 */
export type ActiveTenant = {
  /** Cookie-authoritative finalized tenant (`getSelectedTenantId()`). */
  activeTenantId: string | null;
  /** Super-admin sidebar pick (localStorage); `null` means All Tenants. */
  selectedTenantId: string | null;
  /** What page data fetches scope by: `superAdmin ? selectedTenantId : null`. */
  scopedTenantId: string | null;
  isSuperAdmin: boolean;
  /** Super-admin "pick a tenant to view" gate: `isSuperAdmin && !scopedTenantId`. */
  needsTenant: boolean;
  /** Sidebar writer: persists to localStorage and updates state. Super-admin only. */
  setSelectedTenant: (tenantId: string | null) => void;
};

/** UI capability flags (camelCase mirror of the backend `Capabilities`). */
export type CapabilityFlags = {
  canManageProcesses: boolean;
  canReadSecrets: boolean;
  canManageSecrets: boolean;
  canReadConnectors: boolean;
  canManageConnectorProfiles: boolean;
  canManageTenant: boolean;
};

/** The tenant directory — super-admin registry rows + non-admin org display. */
export type TenantRegistry = {
  tenants: TenantSummary[];
  refreshTenants: () => void;
  organizationMemberships: OrganizationMembership[];
  activeTenantLabel: string | null;
};

export type SessionContextValue = {
  activeTenant: ActiveTenant;
  capabilities: CapabilityFlags;
  registry: TenantRegistry;
};

/**
 * `null` when read outside a `SessionProvider` — the hooks throw on that so a
 * missing provider is a loud error, not a silent undefined.
 */
export const SessionContext = createContext<SessionContextValue | null>(null);

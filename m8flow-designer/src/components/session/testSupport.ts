import type { TenantSummary } from '@/lib/api';
import type { ActiveTenant, CapabilityFlags, TenantRegistry } from './SessionContext';

/**
 * Test-only fixture shape for the session hooks — the flat bag page tests build
 * to describe a session. Formerly `AppShell`'s outlet-context type; it now lives
 * here because AppShell no longer provides an outlet context. The three
 * `*FromContext` helpers map it to the hook return values.
 */
export type SessionFixtureContext = {
  scopedTenantId: string | null;
  selectedTenantId: string | null;
  isSuperAdmin: boolean;
  canManageProcesses?: boolean;
  canManageProcessModels?: boolean;
  canStartProcesses?: boolean;
  canReviewTasks?: boolean;
  canReadProcesses?: boolean;
  canReadProcessInstances?: boolean;
  canReadSecrets?: boolean;
  canManageSecrets?: boolean;
  canReadConnectors?: boolean;
  canReadMcpConnection?: boolean;
  canReadMessages?: boolean;
  canReadTemplates?: boolean;
  canManageConnectorProfiles?: boolean;
  canManageTenant?: boolean;
  refreshTenants?: () => void;
  tenants?: TenantSummary[];
};

/**
 * Derive `useActiveTenant()` return values from the fixture, with identical
 * semantics to production (notably `needsTenant = isSuperAdmin && !scopedTenantId`).
 */
export function activeTenantFromContext(ctx: SessionFixtureContext): ActiveTenant {
  return {
    activeTenantId: ctx.scopedTenantId,
    selectedTenantId: ctx.selectedTenantId,
    scopedTenantId: ctx.scopedTenantId,
    isSuperAdmin: ctx.isSuperAdmin,
    needsTenant: ctx.isSuperAdmin && !ctx.scopedTenantId,
    needsTenantForWrite: ctx.isSuperAdmin && !ctx.scopedTenantId,
    setSelectedTenant: () => {},
  };
}

export function capabilitiesFromContext(ctx: SessionFixtureContext): CapabilityFlags {
  return {
    canStartProcesses: Boolean(ctx.canStartProcesses ?? ctx.canManageProcesses),
    canReviewTasks: Boolean(ctx.canReviewTasks),
    canReadProcesses: Boolean(ctx.canReadProcesses),
    canReadProcessInstances: Boolean(ctx.canReadProcessInstances),
    canManageProcesses: Boolean(ctx.canManageProcesses),
    canManageProcessModels: Boolean(ctx.canManageProcessModels),
    canReadSecrets: Boolean(ctx.canReadSecrets),
    canManageSecrets: Boolean(ctx.canManageSecrets),
    canReadConnectors: Boolean(ctx.canReadConnectors),
    canReadMcpConnection: Boolean(ctx.canReadMcpConnection),
    canReadMessages: Boolean(ctx.canReadMessages),
    canReadTemplates: Boolean(ctx.canReadTemplates),
    canManageConnectorProfiles: Boolean(ctx.canManageConnectorProfiles),
    canManageTenant: Boolean(ctx.canManageTenant),
  };
}

export function tenantRegistryFromContext(ctx: SessionFixtureContext): TenantRegistry {
  return {
    tenants: ctx.tenants ?? [],
    refreshTenants: ctx.refreshTenants ?? (() => {}),
    organizationMemberships: [],
    activeTenantLabel: null,
  };
}

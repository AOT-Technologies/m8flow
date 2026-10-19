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
  canReadTaskReview?: boolean;
  canReadHomeTaskCount?: boolean;
  canReadProcesses?: boolean;
  canReadProcessInstances?: boolean;
  canReadSecrets?: boolean;
  canManageSecrets?: boolean;
  canReadConnectors?: boolean;
  canReadMcpConnection?: boolean;
  canReadMcpTools?: boolean;
  canExecuteMcpTools?: boolean;
  canReadMessages?: boolean;
  canReadNatsMonitoring?: boolean;
  canReadNatsEvents?: boolean;
  canReadTemplates?: boolean;
  canManageConnectorProfiles?: boolean;
  canManageTenant?: boolean;
  canAccessTenantManagement?: boolean;
  canReadNatsApiKeys?: boolean;
  canManageNatsApiKeys?: boolean;
  canCreateProcessModels?: boolean;
  canDeleteProcessModels?: boolean;
  canCreateProcessGroups?: boolean;
  canUpdateProcessGroups?: boolean;
  canDeleteProcessGroups?: boolean;
  canCopyProcessModels?: boolean;
  canRunProcessModelTests?: boolean;
  canCreateScriptUnitTests?: boolean;
  canRunScriptUnitTests?: boolean;
  canCreateProcessModelFiles?: boolean;
  canUpdateProcessModelFiles?: boolean;
  canDeleteProcessModelFiles?: boolean;
  canSuspendProcessInstances?: boolean;
  canResumeProcessInstances?: boolean;
  canTerminateProcessInstances?: boolean;
  canDeleteProcessInstances?: boolean;
  canCreateTemplates?: boolean;
  canImportTemplates?: boolean;
  canUpdateTemplates?: boolean;
  canDeleteTemplates?: boolean;
  canRestoreTemplates?: boolean;
  canUpdateTemplateFiles?: boolean;
  canDeleteTemplateFiles?: boolean;
  canCreateProcessModelsFromTemplates?: boolean;
  canCreateConnectorProfiles?: boolean;
  canUpdateConnectorProfiles?: boolean;
  canDeleteConnectorProfiles?: boolean;
  canCreateSecrets?: boolean;
  canUpdateSecrets?: boolean;
  canDeleteSecrets?: boolean;
  canCreateTenants?: boolean;
  canUpdateTenants?: boolean;
  canManageTenantMembers?: boolean;
  canManageTenantGroups?: boolean;
  canAddTenantMembers?: boolean;
  canRemoveTenantMembers?: boolean;
  canCreateTenantGroups?: boolean;
  canUpdateTenantGroups?: boolean;
  canDeleteTenantGroups?: boolean;
  canUpdateTenantGroupMemberships?: boolean;
  canUpdateTenantGroupRoles?: boolean;
  canSubmitTaskReviews?: boolean;
  canRevokeNatsApiKeys?: boolean;
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
    canReviewTasks: Boolean(ctx.canReviewTasks ?? ctx.canSubmitTaskReviews),
    canReadTaskReview: Boolean(ctx.canReadTaskReview),
    canReadHomeTaskCount: Boolean(ctx.canReadHomeTaskCount),
    canReadProcesses: Boolean(ctx.canReadProcesses),
    canReadProcessInstances: Boolean(ctx.canReadProcessInstances),
    canManageProcesses: Boolean(ctx.canManageProcesses),
    canManageProcessModels: Boolean(ctx.canManageProcessModels),
    canReadSecrets: Boolean(ctx.canReadSecrets),
    canManageSecrets: Boolean(ctx.canManageSecrets ?? ctx.canCreateSecrets ?? ctx.canUpdateSecrets ?? ctx.canDeleteSecrets),
    canReadConnectors: Boolean(ctx.canReadConnectors),
    canReadMcpConnection: Boolean(ctx.canReadMcpConnection),
    canReadMcpTools: Boolean(ctx.canReadMcpTools),
    canExecuteMcpTools: Boolean(ctx.canExecuteMcpTools),
    canReadMessages: Boolean(ctx.canReadMessages),
    canReadNatsMonitoring: Boolean(ctx.canReadNatsMonitoring),
    canReadNatsEvents: Boolean(ctx.canReadNatsEvents),
    canReadTemplates: Boolean(ctx.canReadTemplates),
    canManageConnectorProfiles: Boolean(ctx.canManageConnectorProfiles ?? ctx.canCreateConnectorProfiles ?? ctx.canUpdateConnectorProfiles ?? ctx.canDeleteConnectorProfiles),
    canManageTenant: Boolean(ctx.canManageTenant),
    canAccessTenantManagement: Boolean(ctx.canAccessTenantManagement ?? ctx.canManageTenant),
    canReadNatsApiKeys: Boolean(ctx.canReadNatsApiKeys),
    canManageNatsApiKeys: Boolean(ctx.canManageNatsApiKeys),
    canCreateProcessModels: Boolean(ctx.canCreateProcessModels ?? ctx.canManageProcesses),
    canDeleteProcessModels: Boolean(ctx.canDeleteProcessModels ?? ctx.canManageProcesses),
    canCreateProcessGroups: Boolean(ctx.canCreateProcessGroups ?? ctx.canManageProcesses),
    canUpdateProcessGroups: Boolean(ctx.canUpdateProcessGroups ?? ctx.canManageProcesses),
    canDeleteProcessGroups: Boolean(ctx.canDeleteProcessGroups ?? ctx.canManageProcesses),
    canCopyProcessModels: Boolean(ctx.canCopyProcessModels ?? ctx.canManageProcesses),
    canRunProcessModelTests: Boolean(ctx.canRunProcessModelTests ?? ctx.canManageProcesses),
    canCreateScriptUnitTests: Boolean(ctx.canCreateScriptUnitTests ?? ctx.canManageProcesses),
    canRunScriptUnitTests: Boolean(ctx.canRunScriptUnitTests ?? ctx.canManageProcesses),
    canCreateProcessModelFiles: Boolean(ctx.canCreateProcessModelFiles ?? ctx.canManageProcesses),
    canUpdateProcessModelFiles: Boolean(ctx.canUpdateProcessModelFiles ?? ctx.canManageProcessModels),
    canDeleteProcessModelFiles: Boolean(ctx.canDeleteProcessModelFiles ?? ctx.canManageProcesses),
    canSuspendProcessInstances: Boolean(ctx.canSuspendProcessInstances ?? ctx.canManageProcesses),
    canResumeProcessInstances: Boolean(ctx.canResumeProcessInstances ?? ctx.canManageProcesses),
    canTerminateProcessInstances: Boolean(ctx.canTerminateProcessInstances ?? ctx.canManageProcesses),
    canDeleteProcessInstances: Boolean(ctx.canDeleteProcessInstances ?? ctx.canManageProcesses),
    canCreateTemplates: Boolean(ctx.canCreateTemplates ?? ctx.canManageProcesses),
    canImportTemplates: Boolean(ctx.canImportTemplates ?? ctx.canManageProcesses),
    canUpdateTemplates: Boolean(ctx.canUpdateTemplates ?? ctx.canManageProcesses),
    canDeleteTemplates: Boolean(ctx.canDeleteTemplates ?? ctx.canManageProcesses),
    canRestoreTemplates: Boolean(ctx.canRestoreTemplates ?? ctx.canManageProcesses),
    canUpdateTemplateFiles: Boolean(ctx.canUpdateTemplateFiles ?? ctx.canManageProcesses),
    canDeleteTemplateFiles: Boolean(ctx.canDeleteTemplateFiles ?? ctx.canManageProcesses),
    canCreateProcessModelsFromTemplates: Boolean(ctx.canCreateProcessModelsFromTemplates ?? ctx.canManageProcesses),
    canCreateConnectorProfiles: Boolean(ctx.canCreateConnectorProfiles ?? ctx.canManageConnectorProfiles),
    canUpdateConnectorProfiles: Boolean(ctx.canUpdateConnectorProfiles ?? ctx.canManageConnectorProfiles),
    canDeleteConnectorProfiles: Boolean(ctx.canDeleteConnectorProfiles ?? ctx.canManageConnectorProfiles),
    canCreateSecrets: Boolean(ctx.canCreateSecrets ?? ctx.canManageSecrets),
    canUpdateSecrets: Boolean(ctx.canUpdateSecrets ?? ctx.canManageSecrets),
    canDeleteSecrets: Boolean(ctx.canDeleteSecrets ?? ctx.canManageSecrets),
    canCreateTenants: Boolean(ctx.canCreateTenants),
    canUpdateTenants: Boolean(ctx.canUpdateTenants ?? ctx.canManageTenant),
    canManageTenantMembers: Boolean(ctx.canManageTenantMembers ?? ctx.canManageTenant),
    canManageTenantGroups: Boolean(ctx.canManageTenantGroups ?? ctx.canManageTenant),
    canAddTenantMembers: Boolean(ctx.canAddTenantMembers ?? ctx.canManageTenant),
    canRemoveTenantMembers: Boolean(ctx.canRemoveTenantMembers ?? ctx.canManageTenant),
    canCreateTenantGroups: Boolean(ctx.canCreateTenantGroups ?? ctx.canManageTenant),
    canUpdateTenantGroups: Boolean(ctx.canUpdateTenantGroups ?? ctx.canManageTenant),
    canDeleteTenantGroups: Boolean(ctx.canDeleteTenantGroups ?? ctx.canManageTenant),
    canUpdateTenantGroupMemberships: Boolean(ctx.canUpdateTenantGroupMemberships ?? ctx.canManageTenant),
    canUpdateTenantGroupRoles: Boolean(ctx.canUpdateTenantGroupRoles ?? ctx.canManageTenant),
    canSubmitTaskReviews: Boolean(ctx.canSubmitTaskReviews ?? ctx.canReviewTasks),
    canRevokeNatsApiKeys: Boolean(ctx.canRevokeNatsApiKeys ?? ctx.canManageNatsApiKeys),
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

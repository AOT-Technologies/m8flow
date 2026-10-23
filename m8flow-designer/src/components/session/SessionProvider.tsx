import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { checkPermissions, fetchCapabilities, fetchOrganizationMemberships, fetchTenants, type TenantSummary } from '@/lib/api';
import {
  getActiveTenantDisplayLabel,
  getSelectedTenantId,
  isSuperAdmin,
  type OrganizationMembership,
} from '@/lib/auth';
import { persistTenantId, readPersistedTenantId } from '@/lib/selectedTenant';
import { SessionContext, type SessionContextValue } from './SessionContext';
import { buildPermissionCheckRequest, hasPermission } from './permissionCheckTargets';

const NO_OPERATION_PERMISSIONS = {
  canCreateProcessModels: false,
  canDeleteProcessModels: false,
  canCreateProcessGroups: false,
  canUpdateProcessGroups: false,
  canDeleteProcessGroups: false,
  canCopyProcessModels: false,
  canRunProcessModelTests: false,
  canCreateScriptUnitTests: false,
  canRunScriptUnitTests: false,
  canCreateProcessModelFiles: false,
  canUpdateProcessModelFiles: false,
  canDeleteProcessModelFiles: false,
  canSuspendProcessInstances: false,
  canResumeProcessInstances: false,
  canTerminateProcessInstances: false,
  canDeleteProcessInstances: false,
  canCreateTemplates: false,
  canImportTemplates: false,
  canUpdateTemplates: false,
  canDeleteTemplates: false,
  canRestoreTemplates: false,
  canUpdateTemplateFiles: false,
  canDeleteTemplateFiles: false,
  canCreateProcessModelsFromTemplates: false,
  canCreateConnectorProfiles: false,
  canUpdateConnectorProfiles: false,
  canDeleteConnectorProfiles: false,
  canCreateSecrets: false,
  canUpdateSecrets: false,
  canDeleteSecrets: false,
  canCreateTenants: false,
  canUpdateTenants: false,
  canManageTenantMembers: false,
  canManageTenantGroups: false,
  canAddTenantMembers: false,
  canRemoveTenantMembers: false,
  canCreateTenantGroups: false,
  canUpdateTenantGroups: false,
  canDeleteTenantGroups: false,
  canUpdateTenantGroupMemberships: false,
  canUpdateTenantGroupRoles: false,
  canSubmitTaskReviews: false,
  canReadHomeTaskCount: false,
  canRevokeNatsApiKeys: false,
};

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
  const [canManageProcessModels, setCanManageProcessModels] = useState(false);
  const [canStartProcesses, setCanStartProcesses] = useState(false);
  const [canReviewTasks, setCanReviewTasks] = useState(false);
  const [canReadTaskReview, setCanReadTaskReview] = useState(false);
  const [canReadProcesses, setCanReadProcesses] = useState(false);
  const [canReadProcessInstances, setCanReadProcessInstances] = useState(false);
  const [capabilityStatus, setCapabilityStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [canReadSecrets, setCanReadSecrets] = useState(false);
  const [canManageSecrets, setCanManageSecrets] = useState(false);
  const [canReadConnectors, setCanReadConnectors] = useState(false);
  const [canReadMcpConnection, setCanReadMcpConnection] = useState(false);
  const [canReadMcpTools, setCanReadMcpTools] = useState(false);
  const [canExecuteMcpTools, setCanExecuteMcpTools] = useState(false);
  const [canReadMessages, setCanReadMessages] = useState(false);
  const [canReadNatsMonitoring, setCanReadNatsMonitoring] = useState(false);
  const [canReadNatsEvents, setCanReadNatsEvents] = useState(false);
  const [canReadTemplates, setCanReadTemplates] = useState(false);
  const [canManageConnectorProfiles, setCanManageConnectorProfiles] = useState(false);
  const [canManageTenant, setCanManageTenant] = useState(false);
  const [canAccessTenantManagement, setCanAccessTenantManagement] = useState(false);
  const [canReadNatsApiKeys, setCanReadNatsApiKeys] = useState(false);
  const [canManageNatsApiKeys, setCanManageNatsApiKeys] = useState(false);
  const [operationPermissions, setOperationPermissions] = useState(NO_OPERATION_PERMISSIONS);

  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [tenantsReloadKey, setTenantsReloadKey] = useState(0);
  const [organizationMemberships, setOrganizationMemberships] = useState<OrganizationMembership[]>([]);
  const [activeTenantLabel, setActiveTenantLabel] = useState<string | null>(() =>
    superAdmin ? null : getActiveTenantDisplayLabel(),
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchCapabilities(),
      checkPermissions({
        ...buildPermissionCheckRequest(),
        '/m8flow/mcp-connection': ['GET'],
        '/m8flow/mcp-tools': ['GET'],
        '/m8flow/mcp-tools/execute': ['POST'],
      }),
    ])
      .then(([caps, permissions]) => {
        if (!cancelled) {
          const processWrites = Boolean(permissions['/process-models']?.POST);
          setCanReadProcesses(hasPermission(permissions, 'readProcessModels'));
          setCanReadProcessInstances(hasPermission(permissions, 'readProcessInstances'));
          setCanReadMcpConnection(hasPermission(permissions, 'readMcpConnection'));
          setCanReadMessages(hasPermission(permissions, 'readMessages'));
          setCanReadNatsMonitoring(hasPermission(permissions, 'readNatsMonitoring'));
          setCanReadNatsEvents(hasPermission(permissions, 'readNatsEvents'));
          setCanReadTemplates(hasPermission(permissions, 'readTemplates'));
          setCanReadTaskReview(hasPermission(permissions, 'readTaskReview'));
          setCanReadMcpTools(Boolean(permissions['/m8flow/mcp-tools']?.GET));
          setCanExecuteMcpTools(Boolean(permissions['/m8flow/mcp-tools/execute']?.POST));
          setCanManageProcesses(processWrites && Boolean(caps.can_manage_processes));
          setCanManageProcessModels(Boolean(permissions['/process-models']?.PUT));
          setCanStartProcesses(Boolean(permissions['/process-instances']?.POST));
          setCanReviewTasks(Boolean(caps.can_review_tasks));
          setCapabilityStatus('ready');
          setCanReadSecrets(Boolean(permissions['/secrets']?.GET));
          setCanManageSecrets(Boolean(caps.can_manage_secrets));
          setCanReadConnectors(Boolean(permissions['/m8flow/connectors-grouped']?.GET));
          setCanManageConnectorProfiles(Boolean(caps.can_manage_connector_profiles));
          setCanManageTenant(Boolean(caps.can_manage_tenant));
          setCanAccessTenantManagement(hasPermission(permissions, 'readTenantManagement'));
          setCanReadNatsApiKeys(hasPermission(permissions, 'readNatsApiKeys'));
          setCanManageNatsApiKeys(hasPermission(permissions, 'createNatsApiKeys'));
          setOperationPermissions({
            canCreateProcessModels: Boolean(permissions['/process-models']?.POST),
            canDeleteProcessModels: Boolean(permissions['/process-models/capability-check']?.DELETE),
            canCreateProcessGroups: Boolean(permissions['/process-groups']?.POST),
            canUpdateProcessGroups: Boolean(permissions['/process-groups/{id}']?.PUT),
            canDeleteProcessGroups: Boolean(permissions['/process-groups/{id}']?.DELETE),
            canCopyProcessModels: Boolean(permissions['/process-models/{id}/copy']?.POST),
            canRunProcessModelTests: Boolean(permissions['/process-models/{id}/tests/run']?.POST),
            canCreateScriptUnitTests: Boolean(permissions['/process-models/{id}/script-unit-tests']?.POST),
            canRunScriptUnitTests: Boolean(permissions['/process-models/{id}/script-unit-tests/run']?.POST),
            canCreateProcessModelFiles: Boolean(permissions['/process-models/{id}/files']?.POST),
            canUpdateProcessModelFiles: Boolean(permissions['/process-models/{id}/files/{file}']?.PUT),
            canDeleteProcessModelFiles: Boolean(permissions['/process-models/{id}/files/{file}']?.DELETE),
            canSuspendProcessInstances: Boolean(permissions['/process-instances/{id}/suspend']?.POST),
            canResumeProcessInstances: Boolean(permissions['/process-instances/{id}/resume']?.POST),
            canTerminateProcessInstances: Boolean(permissions['/process-instances/{id}/terminate']?.POST),
            canDeleteProcessInstances: Boolean(permissions['/process-instances/{id}']?.DELETE),
            canCreateTemplates: Boolean(permissions['/m8flow/templates']?.POST),
            canImportTemplates: Boolean(permissions['/m8flow/templates/import']?.POST),
            canUpdateTemplates: Boolean(permissions['/m8flow/templates/{id}']?.PUT),
            canDeleteTemplates: Boolean(permissions['/m8flow/templates/{id}']?.DELETE),
            canRestoreTemplates: Boolean(permissions['/m8flow/templates/{id}/restore']?.POST),
            canUpdateTemplateFiles: Boolean(permissions['/m8flow/templates/{id}/files/{file}']?.PUT),
            canDeleteTemplateFiles: Boolean(permissions['/m8flow/templates/{id}/files/{file}']?.DELETE),
            canCreateProcessModelsFromTemplates: Boolean(permissions['/m8flow/templates/{id}/create-process-model']?.POST),
            canCreateConnectorProfiles: Boolean(permissions['/m8flow/connector-profiles']?.POST),
            canUpdateConnectorProfiles: Boolean(permissions['/m8flow/connector-profiles/{id}']?.PUT),
            canDeleteConnectorProfiles: Boolean(permissions['/m8flow/connector-profiles/{id}']?.DELETE),
            canCreateSecrets: Boolean(permissions['/secrets']?.POST),
            canUpdateSecrets: Boolean(permissions['/secrets/{key}']?.PUT),
            canDeleteSecrets: Boolean(permissions['/secrets/{key}']?.DELETE),
            canCreateTenants: Boolean(permissions['/m8flow/tenant-realms']?.POST),
            canUpdateTenants: Boolean(permissions['/m8flow/tenants/{id}']?.PUT),
            canManageTenantMembers: Boolean(permissions['/m8flow/tenants/{id}/members']?.POST)
              || Boolean(permissions['/m8flow/tenants/{id}/members/{username}']?.DELETE),
            canManageTenantGroups: Boolean(permissions['/m8flow/tenants/{id}/groups']?.POST)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}']?.PUT)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}']?.DELETE)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/members/{username}']?.PUT)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/members/{username}']?.DELETE)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/roles/{role}']?.PUT)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/roles/{role}']?.DELETE),
            canAddTenantMembers: Boolean(permissions['/m8flow/tenants/{id}/members']?.POST),
            canRemoveTenantMembers: Boolean(permissions['/m8flow/tenants/{id}/members/{username}']?.DELETE),
            canCreateTenantGroups: Boolean(permissions['/m8flow/tenants/{id}/groups']?.POST),
            canUpdateTenantGroups: Boolean(permissions['/m8flow/tenants/{id}/groups/{group}']?.PUT),
            canDeleteTenantGroups: Boolean(permissions['/m8flow/tenants/{id}/groups/{group}']?.DELETE),
            canUpdateTenantGroupMemberships: Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/members/{username}']?.PUT)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/members/{username}']?.DELETE),
            canUpdateTenantGroupRoles: Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/roles/{role}']?.PUT)
              || Boolean(permissions['/m8flow/tenants/{id}/groups/{group}/roles/{role}']?.DELETE),
            canSubmitTaskReviews: Boolean(permissions['/m8flow/task-review-access/{id}/submit']?.POST),
            canReadHomeTaskCount: hasPermission(permissions, 'readHomeTaskCount'),
            canRevokeNatsApiKeys: Boolean(permissions['/m8flow/nats-tokens/{id}']?.DELETE),
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCanManageProcesses(false);
          setCanManageProcessModels(false);
          setCanReadProcesses(false);
          setCanReadProcessInstances(false);
          setCapabilityStatus('error');
          setCanReadSecrets(false);
          setCanManageSecrets(false);
          setCanReadConnectors(false);
          setCanReadMcpConnection(false);
          setCanReadMcpTools(false);
          setCanExecuteMcpTools(false);
          setCanReadMessages(false);
          setCanReadNatsMonitoring(false);
          setCanReadNatsEvents(false);
          setCanReadTemplates(false);
          setCanReadTaskReview(false);
          setCanManageConnectorProfiles(false);
          setCanManageTenant(false);
          setCanAccessTenantManagement(false);
          setCanReadNatsApiKeys(false);
          setCanManageNatsApiKeys(false);
          setOperationPermissions(NO_OPERATION_PERMISSIONS);
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
        needsTenantForWrite: superAdmin && !scopedTenantId,
        setSelectedTenant,
      },
      capabilities: {
        status: capabilityStatus,
        canStartProcesses,
        canReviewTasks,
        canReadTaskReview,
        canReadProcesses,
        canReadProcessInstances,
        canManageProcesses,
        canManageProcessModels,
        canReadSecrets,
        canManageSecrets,
        canReadConnectors,
        canReadMcpConnection,
        canReadMcpTools,
        canExecuteMcpTools,
        canReadMessages,
        canReadNatsMonitoring,
        canReadNatsEvents,
        canReadTemplates,
        canManageConnectorProfiles,
        canManageTenant,
        canAccessTenantManagement,
        canReadNatsApiKeys,
        canManageNatsApiKeys,
        ...operationPermissions,
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
      canManageProcessModels,
      capabilityStatus,
      canStartProcesses,
      canReviewTasks,
      canReadTaskReview,
      canReadProcesses,
      canReadProcessInstances,
      canReadSecrets,
      canManageSecrets,
      canReadConnectors,
      canReadMcpConnection,
      canReadMcpTools,
      canExecuteMcpTools,
      canReadMessages,
      canReadNatsMonitoring,
      canReadNatsEvents,
      canReadTemplates,
      canManageConnectorProfiles,
      canManageTenant,
      canAccessTenantManagement,
      canReadNatsApiKeys,
      canManageNatsApiKeys,
      operationPermissions,
      tenants,
      refreshTenants,
      organizationMemberships,
      activeTenantLabel,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  checkPermissions,
  createProcessGroup,
  createProcessModel,
  deleteProcessGroup,
  deleteProcessModel,
  fetchProcessGroups,
  fetchProcessModelDetail,
  fetchProcessModels,
  processModelActionPath,
  publishProcessModel,
  updateProcessGroup,
  updateProcessModel,
  type ProcessGroupListItem,
  type ProcessModelListItem,
  type ProcessModelStatus,
} from '@/lib/api';
import {
  fetchProcessInstanceOwnerOptions,
  type ProcessInstanceOwnerOption,
} from '@/lib/processInstancesApi';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import i18n from '@/i18n';
import { CreateProcessModelDialog } from './components/CreateProcessModelDialog';
import { ProcessGroupsPicker } from './components/ProcessGroupsPicker';
import { ProcessesModelsList } from './components/ProcessesModelsList';
import { encodeProcessModelId } from '@/lib/processModelId';
import { startErrorMessage } from '@/lib/startProcessError';
import { useProcessStart } from '@/components/useProcessStart';

const EMPTY_GROUPS: ProcessGroupListItem[] = [];
const EMPTY_MODELS: ProcessModelListItem[] = [];

/**
 * Processes models list — wired to GET /v1.0/m8flow/process-models.
 * All-Tenants reads retain each model's owning tenant.
 */
export default function ProcessesPage() {
  const { t } = useTranslation();
  const { start, picker } = useProcessStart();
  const { scopedTenantId, isSuperAdmin, needsTenantForWrite } = useActiveTenant();
  // All Tenants renders the merged cross-tenant catalog instead of a gate.
  const allTenants = isSuperAdmin && !scopedTenantId;
  const {
    canManageProcessModels,
    canStartProcesses,
    canCreateProcessModels,
    canDeleteProcessModels,
    canCreateProcessGroups,
    canUpdateProcessGroups,
    canDeleteProcessGroups,
  } = useCapabilities();
  // M8F-479: super-admin may write catalog when a concrete tenant is selected.
  // Catalog writes must target one tenant, so they stay disabled under
  // All Tenants even though the list itself renders.
  const canCreateModel = canCreateProcessModels && !needsTenantForWrite;
  const canDeleteModel = canDeleteProcessModels && !needsTenantForWrite;
  const canCreateGroup = canCreateProcessGroups && !needsTenantForWrite;
  const canUpdateGroup = canUpdateProcessGroups && !needsTenantForWrite;
  const canDeleteGroup = canDeleteProcessGroups && !needsTenantForWrite;
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const groupFilter = searchParams.get('group');
  const groupTenantId = allTenants && groupFilter ? searchParams.get('groupTenantId') || null : null;

  const [modelsState, setModelsState] = useState<{
    tenantId: typeof scopedTenantId;
    rows: ProcessModelListItem[];
    loading: boolean;
    error: string | null;
    allCount: number;
  }>({ tenantId: scopedTenantId, rows: [], loading: true, error: null, allCount: 0 });
  const currentModels = modelsState.tenantId === scopedTenantId ? modelsState : undefined;
  const models = currentModels?.rows ?? EMPTY_MODELS;
  const visibleModels = useMemo(() => groupTenantId
    ? models.filter((model) => model.tenant_id === groupTenantId && model.group_id === groupFilter)
    : models, [models, groupTenantId, groupFilter]);
  const loading = currentModels?.loading ?? true;
  const error = currentModels?.error ?? null;
  const allCount = currentModels?.allCount ?? 0;
  function setError(message: string | null) {
    setModelsState((prev) => prev.tenantId === scopedTenantId ? { ...prev, error: message } : prev);
  }
  const [allowedModelActions, setAllowedModelActions] = useState<{
    tenantId: typeof scopedTenantId; publish: Set<string>; start: Set<string>;
  }>();
  useEffect(() => {
    if (needsTenantForWrite) return;
    const versioned = models.filter((model) => model.working_revision);
    if (!versioned.length) return;
    const request = Object.fromEntries(versioned.flatMap((model) => {
      const id = encodeProcessModelId(model.id);
      return [[processModelActionPath(id, 'publish'), ['POST']], [processModelActionPath(id, 'start'), ['POST']]];
    }));
    let active = true;
    checkPermissions(request).then((permissions) => {
      if (!active) return;
      const allowed = (action: 'publish' | 'start') => new Set(versioned.filter((model) =>
        permissions[processModelActionPath(encodeProcessModelId(model.id), action)]?.POST === true,
      ).map((model) => model.id));
      setAllowedModelActions({ tenantId: scopedTenantId, publish: allowed('publish'), start: allowed('start') });
    }).catch(() => { if (active) setAllowedModelActions(undefined); });
    return () => { active = false; };
  }, [models, needsTenantForWrite, scopedTenantId]);
  // Grants are per model and tenant, not per status, so keep the last answer
  // while a refetched list is re-checked; otherwise Publish and Start vanish
  // after every status change until the check returns.
  const currentActions = allowedModelActions?.tenantId === scopedTenantId ? allowedModelActions : undefined;
  const [owners, setOwners] = useState<ProcessInstanceOwnerOption[]>([]);
  const [ownerFilter, setOwnerFilter] = useState('all');
  const [startPending, setStartPending] = useState(false);

  const [groupsOpen, setGroupsOpen] = useState(false);
  const [groupsCreateMode, setGroupsCreateMode] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [groupsState, setGroupsState] = useState<{
    tenantId: typeof scopedTenantId;
    rows: ProcessGroupListItem[];
    loading: boolean;
    error: string | null;
  }>({ tenantId: scopedTenantId, rows: [], loading: true, error: null });
  // Hide the old scope during render, before the new tenant's effect runs.
  const currentGroups = groupsState.tenantId === scopedTenantId ? groupsState : undefined;
  const groups = currentGroups?.rows ?? EMPTY_GROUPS;
  const groupsLoading = currentGroups?.loading ?? true;
  const groupsError = currentGroups?.error ?? null;
  /** Bumped after a successful delete to re-run the models fetch effect. */
  const [refreshKey, setRefreshKey] = useState(0);
  /** Bumped after group create/edit/delete to refetch the group list. */
  const [groupsRefreshKey, setGroupsRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setModelsState((prev) => ({
      tenantId: scopedTenantId,
      rows: prev.tenantId === scopedTenantId ? prev.rows : [],
      loading: true,
      error: null,
      allCount: prev.tenantId === scopedTenantId ? prev.allCount : 0,
    }));

    const ownerId = ownerFilter === 'all' ? null : Number(ownerFilter);
    const listPromise = fetchProcessModels(
      scopedTenantId,
      groupFilter,
      ownerId,
    );
    const allPromise = groupFilter
      ? fetchProcessModels(
          scopedTenantId,
          null,
          ownerId,
        )
      : listPromise;

    Promise.all([listPromise, allPromise])
      .then(([rows, allRows]) => {
        if (cancelled) {
          return;
        }
        setModelsState({ tenantId: scopedTenantId, rows, allCount: allRows.length, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setModelsState({
            tenantId: scopedTenantId, rows: [], allCount: 0, loading: false,
            error: err instanceof Error ? err.message : i18n.t('processes.page.loadModelsFailed'),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [scopedTenantId, groupFilter, ownerFilter, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    setOwnerFilter('all');

    fetchProcessInstanceOwnerOptions(scopedTenantId)
      .then((rows) => {
        if (!cancelled) {
          setOwners(rows);
        }
      })
      .catch(() => {
        // Owner options are supplementary. A role without process-instance
        // list permission can still use the Processes page.
        if (!cancelled) {
          setOwners([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [scopedTenantId]);

  // Loaded up front: the Group filter dropdown and the Manage groups dialog share it.
  useEffect(() => {
    let cancelled = false;
    setGroupsState((prev) => ({
      tenantId: scopedTenantId,
      rows: prev.tenantId === scopedTenantId ? prev.rows : [],
      loading: true,
      error: null,
    }));

    fetchProcessGroups(scopedTenantId)
      .then((rows) => {
        if (!cancelled) {
          setGroupsState({ tenantId: scopedTenantId, rows, loading: false, error: null });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setGroupsState({
            tenantId: scopedTenantId,
            rows: [],
            loading: false,
            error: err instanceof Error ? err.message : i18n.t('processes.page.loadGroupsFailed'),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [scopedTenantId, groupsRefreshKey]);

  const scopeLabel = useMemo(() => {
    if (!groupFilter) {
      return t('processes.allGroups');
    }
    const fromGroups = groups.find((g) => g.id === groupFilter && (!groupTenantId || g.tenant_id === groupTenantId));
    const match = visibleModels.find((m) => m.group_id === groupFilter);
    const name = fromGroups?.display_name || match?.group_display_name || groupFilter;
    if (!allTenants) return name;
    const tenantName = fromGroups?.tenant_name || match?.tenant_name;
    const tenantLabel = groupTenantId
      ? tenantName && tenantName !== groupTenantId ? `${tenantName} (${groupTenantId})` : groupTenantId
      : t('shell.tenant.allTenants');
    return `${name} — ${tenantLabel}`;
  }, [groupFilter, groupTenantId, visibleModels, groups, allTenants, t]);

  function setGroup(groupId: string | null, tenantId?: string) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (groupId) {
          next.set('group', groupId);
        } else {
          next.delete('group');
        }
        if (groupId && allTenants && tenantId) {
          next.set('groupTenantId', tenantId);
        } else {
          next.delete('groupTenantId');
        }
        return next;
      },
      { replace: true },
    );
  }

  const closeGroups = useCallback(() => {
    setGroupsOpen(false);
    setGroupsCreateMode(false);
  }, []);

  const openGroups = useCallback((createMode = false) => {
    setGroupsCreateMode(createMode);
    setGroupsOpen(true);
  }, []);

  async function handleStartModel(model: ProcessModelListItem) {
    const modifiedId = encodeProcessModelId(model.id);
    const tenantId = model.tenant_id ?? scopedTenantId;
    setError(null);
    setStartPending(true);
    try {
      const detail = await fetchProcessModelDetail(modifiedId, tenantId);
      const result = await start(modifiedId, tenantId, detail.collaboration_participants);
      if (result) navigate(`/process-instances/${result.id}`);
    } catch (err: unknown) {
      setError(startErrorMessage(err, model.display_name));
    } finally {
      setStartPending(false);
    }
  }

  // Rethrows so ProcessesModelsList's confirmation dialog can surface the
  // failure (notably the 409 when the model still has instances); only the
  // success path refreshes the list.
  async function handleDeleteModel(model: ProcessModelListItem) {
    await deleteProcessModel(encodeProcessModelId(model.id), scopedTenantId);
    setRefreshKey((k) => k + 1);
  }

  async function handleChangeModelStatus(
    model: ProcessModelListItem,
    status: ProcessModelStatus,
  ) {
    if (status === 'published' && model.status !== 'paused' && model.working_revision) {
      await publishProcessModel(encodeProcessModelId(model.id), model.working_revision, scopedTenantId);
    } else {
      await updateProcessModel(encodeProcessModelId(model.id), { status }, scopedTenantId, model.working_revision);
    }
    setRefreshKey((k) => k + 1);
  }

  async function handleCreateGroup(input: {
    id: string;
    display_name: string;
    description: string;
  }) {
    const created = await createProcessGroup(input, scopedTenantId);
    // Close and filter to the new group so the user lands on its (empty) model
    // list. Merge it into `groups` so the filter label resolves without a refetch.
    setGroupsState((prev) => prev.tenantId === scopedTenantId ? {
      ...prev, rows: [...prev.rows.filter((g) => g.id !== created.id), created],
    } : prev);
    setGroupsRefreshKey((k) => k + 1);
    setGroup(created.id);
    closeGroups();
  }

  async function handleUpdateGroup(
    groupId: string,
    patch: { display_name: string; description: string },
  ) {
    await updateProcessGroup(groupId, patch, scopedTenantId);
    setGroupsRefreshKey((k) => k + 1);
  }

  async function handleDeleteGroup(groupId: string) {
    await deleteProcessGroup(groupId, scopedTenantId);
    if (groupFilter === groupId) {
      setGroup(null);
    }
    setGroupsRefreshKey((k) => k + 1);
    setRefreshKey((k) => k + 1);
  }

  return (
    <main className="min-w-0 flex-1 px-11 py-10">
      {picker}
      <ProcessesModelsList
        models={visibleModels}
        loading={loading}
        error={error}
        groupFilter={groupFilter}
        groupTenantId={groupTenantId}
        scopeLabel={scopeLabel}
        totalUnfilteredCount={allCount}
        owners={owners}
        ownerFilter={ownerFilter}
        onOwnerFilterChange={setOwnerFilter}
        groups={groups.map((group) => ({
          id: group.id,
          tenantId: allTenants ? group.tenant_id : undefined,
          label: allTenants
            ? `${group.display_name || group.id} — ${group.tenant_name && group.tenant_name !== group.tenant_id
              ? `${group.tenant_name} (${group.tenant_id})` : group.tenant_id}`
            : group.display_name || group.id,
        }))}
        groupsLoading={groupsLoading}
        groupsError={groupsError}
        onRetryGroups={() => {
          if (groupsLoading) return;
          setGroupsState((prev) => ({ ...prev, loading: true, error: null }));
          setGroupsRefreshKey((k) => k + 1);
        }}
        onClearGroupFilter={() => setGroup(null)}
        onFilterByGroup={setGroup}
        showTenant={allTenants}
        onOpenModel={(model) => {
          // Model identifiers are catalog paths and collide across tenants,
          // so carry the row's own tenant into the detail route.
          const suffix = model.tenant_id
            ? `?tenantId=${encodeURIComponent(model.tenant_id)}`
            : '';
          navigate(`/processes/${encodeProcessModelId(model.id)}${suffix}`);
        }}
        onStartModel={!needsTenantForWrite ? handleStartModel : undefined}
        startPending={startPending}
        mayStart={(model) => model.working_revision ? Boolean(currentActions?.start.has(model.id)) : Boolean(canStartProcesses)}
        mayPublish={(model) => model.working_revision ? Boolean(currentActions?.publish.has(model.id)) : Boolean(canManageProcessModels)}
        onDeleteModel={canDeleteModel ? handleDeleteModel : undefined}
        onCreateModel={canCreateModel ? () => setCreateOpen(true) : undefined}
        onChangeModelStatus={
          (canManageProcessModels || currentActions?.publish.size) && !needsTenantForWrite
            ? handleChangeModelStatus : undefined
        }
        mayChangeStatus={canManageProcessModels}
        onManageGroups={
          canCreateGroup || canUpdateGroup || canDeleteGroup ? () => openGroups(true) : undefined
        }
      />
      <CreateProcessModelDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        scopedTenantId={scopedTenantId}
        defaultGroupId={groupFilter}
        onCreateProcessGroup={
          canCreateGroup
            ? () => {
                setCreateOpen(false);
                openGroups(true);
              }
            : undefined
        }
        onCreate={(input) => createProcessModel(input, scopedTenantId)}
        onCreated={(encodedId) => {
          setCreateOpen(false);
          navigate(`/processes/${encodedId}`);
        }}
      />
      <ProcessGroupsPicker
        open={groupsOpen}
        groups={groups}
        loading={groupsLoading}
        error={groupsError}
        canCreate={canCreateGroup}
        canUpdate={canUpdateGroup}
        canDelete={canDeleteGroup}
        startInCreateMode={groupsCreateMode}
        onClose={closeGroups}
        onCreateGroup={canCreateGroup ? handleCreateGroup : undefined}
        onUpdateGroup={canUpdateGroup ? handleUpdateGroup : undefined}
        onDeleteGroup={canDeleteGroup ? handleDeleteGroup : undefined}
      />
    </main>
  );
}

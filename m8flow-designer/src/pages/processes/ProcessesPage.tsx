import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  createProcessGroup,
  createProcessModel,
  deleteProcessGroup,
  deleteProcessModel,
  fetchProcessGroups,
  fetchProcessModels,
  startProcessInstance,
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

/**
 * Processes models list — wired to GET /v1.0/m8flow/process-models.
 * Super-admin must pick a concrete tenant (no All-Tenants catalog merge).
 */
export default function ProcessesPage() {
  const { t } = useTranslation();
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

  const [models, setModels] = useState<ProcessModelListItem[]>([]);
  const [owners, setOwners] = useState<ProcessInstanceOwnerOption[]>([]);
  const [ownerFilter, setOwnerFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  /** Unfiltered count for empty-state copy when a group filter is active. */
  const [allCount, setAllCount] = useState(0);

  const [groupsOpen, setGroupsOpen] = useState(false);
  const [groupsCreateMode, setGroupsCreateMode] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [groups, setGroups] = useState<ProcessGroupListItem[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsError, setGroupsError] = useState<string | null>(null);
  /** Bumped after a successful delete to re-run the models fetch effect. */
  const [refreshKey, setRefreshKey] = useState(0);
  /** Bumped after group create/edit/delete while the picker is open. */
  const [groupsRefreshKey, setGroupsRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

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
        setModels(rows);
        setAllCount(allRows.length);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : i18n.t('processes.page.loadModelsFailed'));
          setModels([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
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

  useEffect(() => {
    if (!groupsOpen) {
      return;
    }

    let cancelled = false;
    setGroupsLoading(true);
    setGroupsError(null);

    fetchProcessGroups(scopedTenantId)
      .then((rows) => {
        if (!cancelled) {
          setGroups(rows);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setGroupsError(err instanceof Error ? err.message : i18n.t('processes.page.loadGroupsFailed'));
          setGroups([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setGroupsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [groupsOpen, scopedTenantId, groupsRefreshKey]);

  const scopeLabel = useMemo(() => {
    if (!groupFilter) {
      return t('processes.allGroups');
    }
    const fromGroups = groups.find((g) => g.id === groupFilter);
    if (fromGroups) {
      return fromGroups.display_name || groupFilter;
    }
    const match = models.find((m) => m.group_id === groupFilter);
    return match?.group_display_name || groupFilter;
  }, [groupFilter, models, groups, t]);

  function setGroup(groupId: string | null) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (groupId) {
          next.set('group', groupId);
        } else {
          next.delete('group');
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
    setError(null);
    try {
      const result = await startProcessInstance(encodeProcessModelId(model.id), scopedTenantId);
      navigate(`/process-instances/${result.id}`);
    } catch (err: unknown) {
      setError(startErrorMessage(err, model.display_name));
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
    await updateProcessModel(encodeProcessModelId(model.id), { status }, scopedTenantId);
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
    setGroups((prev) => [...prev.filter((g) => g.id !== created.id), created]);
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
    <main className="flex-1 px-11 py-10">
      <ProcessesModelsList
        models={models}
        loading={loading}
        error={error}
        groupFilter={groupFilter}
        scopeLabel={scopeLabel}
        totalUnfilteredCount={allCount}
        owners={owners}
        ownerFilter={ownerFilter}
        onOwnerFilterChange={setOwnerFilter}
        onBrowseGroups={() => openGroups()}
        onClearGroupFilter={() => setGroup(null)}
        onFilterByGroup={(groupId) => setGroup(groupId)}
        showTenant={allTenants}
        onOpenModel={(model) => {
          // Model identifiers are catalog paths and collide across tenants,
          // so carry the row's own tenant into the detail route.
          const suffix = model.tenant_id
            ? `?tenantId=${encodeURIComponent(model.tenant_id)}`
            : '';
          navigate(`/processes/${encodeProcessModelId(model.id)}${suffix}`);
        }}
        onStartModel={canStartProcesses && !needsTenantForWrite ? handleStartModel : undefined}
        onDeleteModel={canDeleteModel ? handleDeleteModel : undefined}
        onCreateModel={canCreateModel ? () => setCreateOpen(true) : undefined}
        onChangeModelStatus={
          canManageProcessModels && !needsTenantForWrite ? handleChangeModelStatus : undefined
        }
        onCreateGroup={canCreateGroup ? () => openGroups(true) : undefined}
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
        selectedGroupId={groupFilter}
        canCreate={canCreateGroup}
        canUpdate={canUpdateGroup}
        canDelete={canDeleteGroup}
        startInCreateMode={groupsCreateMode}
        onClose={closeGroups}
        onSelectAll={() => {
          setGroup(null);
          setGroupsOpen(false);
        }}
        onSelectGroup={(groupId) => {
          setGroup(groupId);
          setGroupsOpen(false);
        }}
        onCreateGroup={canCreateGroup ? handleCreateGroup : undefined}
        onUpdateGroup={canUpdateGroup ? handleUpdateGroup : undefined}
        onDeleteGroup={canDeleteGroup ? handleDeleteGroup : undefined}
      />
    </main>
  );
}

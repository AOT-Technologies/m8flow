import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { FolderPlus, Pencil, Shield, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { CheckboxField } from '@/components/library/checkbox-field/CheckboxField';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Pill } from '@/components/library/pill/Pill';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ApiError } from '@/lib/api';
import {
  createTenantGroup,
  deleteTenantGroup,
  fetchTenantGroups,
  grantTenantGroupRole,
  normalizeTenantGroupName,
  renameTenantGroup,
  revokeTenantGroupRole,
  TENANT_GROUP_NAME_MAX_LENGTH,
  TENANT_ROLES,
  tenantAdminErrorMessage,
  type TenantGroup,
  type TenantRole,
  validateTenantGroupName,
} from '@/lib/tenantAdminApi';

const GROUPS_PAGE_SIZE = 10;
const SEARCH_DEBOUNCE_MS = 300;

type TenantGroupsSectionProps = {
  tenantId: string;
  existingGroupNames: string[];
  reloadKey: number;
  canCreate?: boolean;
  canRename?: boolean;
  canDelete?: boolean;
  canUpdateRoles?: boolean;
  onChanged: () => void;
};

function nameTaken(
  candidate: string,
  existingNames: string[],
  exceptName?: string,
): boolean {
  const normalized = normalizeTenantGroupName(candidate).toLowerCase();
  const except = exceptName ? normalizeTenantGroupName(exceptName).toLowerCase() : null;
  return existingNames.some((name) => {
    const current = normalizeTenantGroupName(name).toLowerCase();
    if (except && current === except) {
      return false;
    }
    return current === normalized;
  });
}

function toggledRoles(current: TenantRole[], role: TenantRole): TenantRole[] {
  return current.includes(role)
    ? current.filter((name) => name !== role)
    : TENANT_ROLES.filter((name) => name === role || current.includes(name));
}

export default function TenantGroupsSection({
  tenantId,
  existingGroupNames,
  reloadKey,
  canCreate = false,
  canRename = false,
  canDelete = false,
  canUpdateRoles = false,
  onChanged,
}: TenantGroupsSectionProps) {
  const { t } = useTranslation();
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [groups, setGroups] = useState<TenantGroup[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createRoles, setCreateRoles] = useState<TenantRole[]>([]);
  // Roles that failed to attach to a group that was nevertheless created.
  // Its own state, not `error`: the list's fetch effect owns `error` and
  // clears it on the very reload this warning follows.
  const [createRolesWarning, setCreateRolesWarning] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [groupToRename, setGroupToRename] = useState<TenantGroup | null>(null);
  const [renameName, setRenameName] = useState('');
  const [renameError, setRenameError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);

  const [groupToDelete, setGroupToDelete] = useState<TenantGroup | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [groupForRoles, setGroupForRoles] = useState<TenantGroup | null>(null);
  // Staged picks; nothing reaches the API until Save (M8F-591).
  const [roleSelection, setRoleSelection] = useState<TenantRole[]>([]);
  const [savingRoles, setSavingRoles] = useState(false);
  const [rolesError, setRolesError] = useState<string | null>(null);
  // Bumped on every close, so a save that outlives its dialog (closed while
  // the request hung) drops its result instead of reopening the modal.
  const rolesDialogSession = useRef(0);

  const skipSearchDebounce = useRef(true);

  useEffect(() => {
    if (skipSearchDebounce.current) {
      skipSearchDebounce.current = false;
      return undefined;
    }
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTenantGroups(tenantId, {
      search,
      offset: page * GROUPS_PAGE_SIZE,
      limit: GROUPS_PAGE_SIZE,
    })
      .then((payload) => {
        if (!cancelled) {
          setGroups(payload.groups);
          setHasMore(payload.has_more);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(tenantAdminErrorMessage(err, t('tenantManagement.groups.errors.load')));
          setGroups([]);
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
  }, [tenantId, search, page, reloadKey]);

  const savedRoles = groupForRoles?.mapped_roles ?? [];
  const rolesToGrant = TENANT_ROLES.filter(
    (role) => roleSelection.includes(role) && !savedRoles.includes(role),
  );
  const rolesToRevoke = TENANT_ROLES.filter(
    (role) => !roleSelection.includes(role) && savedRoles.includes(role),
  );
  const rolesDirty = Boolean(groupForRoles) && rolesToGrant.length + rolesToRevoke.length > 0;

  const createValidation = useMemo(() => {
    const formatError = validateTenantGroupName(createName);
    if (formatError) {
      return formatError;
    }
    if (nameTaken(createName, existingGroupNames)) {
      return t('tenantManagement.groups.alreadyExists', { name: normalizeTenantGroupName(createName) });
    }
    return null;
  }, [createName, existingGroupNames, t]);

  const renameValidation = useMemo(() => {
    const formatError = validateTenantGroupName(renameName);
    if (formatError) {
      return formatError;
    }
    if (groupToRename && nameTaken(renameName, existingGroupNames, groupToRename.name)) {
      return t('tenantManagement.groups.alreadyExists', { name: normalizeTenantGroupName(renameName) });
    }
    return null;
  }, [renameName, existingGroupNames, groupToRename, t]);

  function openCreate() {
    setCreateName('');
    setCreateRoles([]);
    setCreateError(null);
    setCreateRolesWarning(null);
    setCreateOpen(true);
  }

  function toggleCreateRole(role: TenantRole) {
    setCreateRoles((current) => toggledRoles(current, role));
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (creating) {
      return;
    }
    const normalized = normalizeTenantGroupName(createName);
    const formatError = validateTenantGroupName(createName);
    if (formatError) {
      setCreateError(formatError);
      return;
    }
    if (nameTaken(createName, existingGroupNames)) {
      setCreateError(t('tenantManagement.groups.alreadyExists', { name: normalized }));
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await createTenantGroup(tenantId, normalized, createRoles);
      setCreateOpen(false);
      setCreateRolesWarning(null);
      onChanged();
    } catch (err: unknown) {
      // 502 group_roles_not_applied means the group exists but its roles did
      // not stick, so the dialog closes and the list carries the warning —
      // reopening a create form for an existing group would only fail on the
      // name. Anything else is a plain failed create.
      if (err instanceof ApiError && err.status === 502) {
        setCreateOpen(false);
        setCreateRolesWarning(
          t('tenantManagement.groups.createRolesWarning', {
            message: tenantAdminErrorMessage(err, t('tenantManagement.groups.errors.rolesNotApplied')),
          }),
        );
        onChanged();
      } else {
        setCreateError(tenantAdminErrorMessage(err, t('tenantManagement.groups.errors.create')));
      }
    } finally {
      setCreating(false);
    }
  }

  function openRename(group: TenantGroup) {
    setGroupToRename(group);
    setRenameName(group.name);
    setRenameError(null);
  }

  async function handleRename(event: FormEvent) {
    event.preventDefault();
    if (!groupToRename || renaming) {
      return;
    }
    const normalized = normalizeTenantGroupName(renameName);
    const formatError = validateTenantGroupName(renameName);
    if (formatError) {
      setRenameError(formatError);
      return;
    }
    if (nameTaken(renameName, existingGroupNames, groupToRename.name)) {
      setRenameError(t('tenantManagement.groups.alreadyExists', { name: normalized }));
      return;
    }
    setRenaming(true);
    setRenameError(null);
    try {
      await renameTenantGroup(tenantId, groupToRename.name, normalized);
      setGroupToRename(null);
      onChanged();
    } catch (err: unknown) {
      setRenameError(tenantAdminErrorMessage(err, t('tenantManagement.groups.errors.rename')));
    } finally {
      setRenaming(false);
    }
  }

  async function handleDelete() {
    if (!groupToDelete || deleting) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await deleteTenantGroup(tenantId, groupToDelete.name);
      setGroupToDelete(null);
      onChanged();
    } catch (err: unknown) {
      setError(tenantAdminErrorMessage(err, t('tenantManagement.groups.errors.delete')));
      setGroupToDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  function openRoles(group: TenantGroup) {
    // Seeding from the loaded list is safe even if it is stale: Save sends
    // per-role deltas, and grant/revoke are idempotent on the backend, so
    // another admin's concurrent changes survive and no-op calls succeed.
    setGroupForRoles(group);
    setRoleSelection(group.mapped_roles);
    setRolesError(null);
  }

  function closeRoles() {
    rolesDialogSession.current += 1;
    setGroupForRoles(null);
  }

  function toggleRole(role: TenantRole) {
    setRoleSelection((current) => toggledRoles(current, role));
  }

  async function handleSaveRoles() {
    if (!groupForRoles || savingRoles || !rolesDirty) {
      return;
    }
    const groupName = groupForRoles.name;
    const session = rolesDialogSession.current;
    setSavingRoles(true);
    setRolesError(null);
    const total = rolesToGrant.length + rolesToRevoke.length;
    let latest = groupForRoles;
    let applied = 0;
    try {
      // Sequential, like member-group saves: each call re-syncs every
      // member's local role assignments, so parallel calls could race.
      for (const role of rolesToGrant) {
        latest = (await grantTenantGroupRole(tenantId, groupName, role)).group;
        applied += 1;
      }
      for (const role of rolesToRevoke) {
        latest = (await revokeTenantGroupRole(tenantId, groupName, role)).group;
        applied += 1;
      }
      if (session === rolesDialogSession.current) {
        closeRoles();
      }
      onChanged();
    } catch (err: unknown) {
      if (applied > 0) {
        onChanged();
      }
      if (session !== rolesDialogSession.current) {
        return;
      }
      // Keep the user's picks but rebase on what the server now has, so the
      // unsaved diff and a retried Save cover only what did not land.
      setGroupForRoles(latest);
      const message = tenantAdminErrorMessage(err, t('tenantManagement.groups.errors.updateRoles'));
      setRolesError(
        applied > 0
          ? t('tenantManagement.groups.partialRolesSave', { applied, total, message })
          : message,
      );
    } finally {
      setSavingRoles(false);
    }
  }

  const columns: DataTableColumn<TenantGroup>[] = [
    {
      key: 'name',
      header: t('tenantManagement.groups.columnGroup'),
      width: 'minmax(140px,1.4fr)',
      render: (group) => (
        <span className="font-medium text-foreground" data-testid={`tenant-group-name-cell-${group.id}`}>
          {group.name}
        </span>
      ),
    },
    {
      key: 'roles',
      header: t('tenantManagement.groups.columnRoles'),
      width: 'minmax(160px,1.6fr)',
      render: (group) => (
        <div className="flex flex-wrap gap-1">
          {group.mapped_roles.length === 0 ? (
            <span className="text-muted-foreground">{t('common.none')}</span>
          ) : (
            group.mapped_roles.map((role) => (
              <Pill
                key={role}
                tone="info"
                dot={false}
                data-testid={`tenant-group-role-chip-${group.id}-${role}`}
              >
                {role}
              </Pill>
            ))
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">{t('common.actions')}</span>,
      className: 'text-right whitespace-nowrap',
      width: 'minmax(220px,1fr)',
      render: (group) => (
        <div className="flex items-center justify-end gap-1">
          {canRename ? <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => openRename(group)}
            data-testid={`tenant-group-rename-button-${group.name}`}
          >
            <Pencil className="size-3.5" aria-hidden />
            {t('tenantManagement.groups.rename')}
          </Button> : null}
          {canUpdateRoles ? <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => openRoles(group)}
            data-testid={`tenant-group-manage-roles-button-${group.name}`}
          >
            <Shield className="size-3.5" aria-hidden />
            {t('tenantManagement.groups.roles')}
          </Button> : null}
          {canDelete ? <Button
            type="button"
            variant="ghost-destructive"
            size="sm"
            onClick={() => setGroupToDelete(group)}
            data-testid={`tenant-group-remove-button-${group.name}`}
          >
            <Trash2 className="size-3.5" aria-hidden />
            {t('common.delete')}
          </Button> : null}
        </div>
      ),
    },
  ];

  return (
    <>
      {error ? (
        <Alert tone="error" className="mb-4">
          {error}
        </Alert>
      ) : null}

      {createRolesWarning ? (
        <Alert tone="warning" className="mb-4" data-testid="tenant-group-create-roles-warning">
          {createRolesWarning}
        </Alert>
      ) : null}

      <Card variant="bordered" className="overflow-hidden">
        <div
          className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-[22px] py-3"
          data-testid="tenant-groups-toolbar"
        >
          <SearchBar
            value={searchInput}
            onChange={setSearchInput}
            placeholder={t('tenantManagement.groups.searchPlaceholder')}
            aria-label={t('tenantManagement.groups.searchLabel')}
            data-testid="tenant-group-search-input"
            className="min-w-0 flex-1"
          />
          {canCreate ? <Button
            type="button"
            variant="pill-dark"
            size="pill"
            onClick={openCreate}
            data-testid="tenant-group-add-button"
          >
            <FolderPlus className="size-3.5" aria-hidden />
            {t('tenantManagement.groups.addGroup')}
          </Button> : null}
        </div>

        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">
            {t('tenantManagement.groups.loading')}
          </p>
        ) : groups.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">
            {search ? t('tenantManagement.groups.noMatch') : t('tenantManagement.groups.empty')}
          </p>
        ) : (
          <DataTable
            columns={columns}
            rows={groups}
            getRowKey={(group) => group.id || group.name}
            data-testid="tenant-group-table-container"
          />
        )}

        <div className="px-[22px] py-3">
          <Pagination
            page={page + 1}
            onPageChange={(nextPage) => setPage(nextPage - 1)}
            hasMore={hasMore}
          />
        </div>
      </Card>

      <Modal
        open={createOpen}
        onOpenChange={setCreateOpen}
        title={t('tenantManagement.groups.create.title')}
        footer={
          <>
            <Button type="button" variant="pill-cancel" size="pill" onClick={() => setCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              form="tenant-group-create-form"
              variant="pill-dark"
              size="pill"
              disabled={creating || Boolean(createValidation)}
              data-testid="tenant-group-submit-button"
            >
              {creating ? t('tenantManagement.groups.create.creating') : t('tenantManagement.groups.create.submit')}
            </Button>
          </>
        }
      >
        <form id="tenant-group-create-form" onSubmit={(event) => void handleCreate(event)}>
          <p className="text-[13.5px] text-muted-foreground">
            {t('tenantManagement.groups.create.hint')}
          </p>
          <label className="mt-4 block text-sm font-medium text-foreground">
            {t('tenantManagement.groups.create.groupName')}
            <Input
              className="mt-1.5"
              value={createName}
              onChange={(event) => {
                setCreateName(event.target.value);
                setCreateError(null);
              }}
              autoComplete="off"
              maxLength={TENANT_GROUP_NAME_MAX_LENGTH}
              data-testid="tenant-group-name-input"
              required
            />
          </label>
          {canUpdateRoles ? <fieldset className="mt-4">
            <legend className="text-sm font-medium text-foreground">
              {t('tenantManagement.groups.create.rolesOptional')}
            </legend>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              {t('tenantManagement.groups.create.rolesHint')}
            </p>
            <div className="mt-2 flex flex-col gap-1">
              {TENANT_ROLES.map((role) => (
                <CheckboxField
                  key={role}
                  label={role}
                  checked={createRoles.includes(role)}
                  onCheckedChange={() => toggleCreateRole(role)}
                  data-testid={`tenant-group-create-role-checkbox-${role}`}
                />
              ))}
            </div>
          </fieldset> : null}
          {createError || (createName && createValidation) ? (
            <Alert tone="error" className="mt-3">
              {createError || createValidation}
            </Alert>
          ) : null}
        </form>
      </Modal>

      <Modal
        open={Boolean(groupToRename)}
        onOpenChange={(open) => !open && setGroupToRename(null)}
        title={t('tenantManagement.groups.renameDialog.title')}
        footer={
          <>
            <Button
              type="button"
              variant="pill-cancel"
              size="pill"
              onClick={() => setGroupToRename(null)}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              form="tenant-group-rename-form"
              variant="pill-dark"
              size="pill"
              disabled={renaming || Boolean(renameValidation)}
              data-testid="tenant-group-rename-submit-button"
            >
              {renaming ? t('tenantManagement.saving') : t('tenantManagement.save')}
            </Button>
          </>
        }
      >
        <form id="tenant-group-rename-form" onSubmit={(event) => void handleRename(event)}>
          <p className="text-[13.5px] text-muted-foreground">
            {t('tenantManagement.groups.renameDialog.hint')}
          </p>
          <label className="mt-4 block text-sm font-medium text-foreground">
            {t('tenantManagement.groups.create.groupName')}
            <Input
              className="mt-1.5"
              value={renameName}
              onChange={(event) => {
                setRenameName(event.target.value);
                setRenameError(null);
              }}
              autoComplete="off"
              maxLength={TENANT_GROUP_NAME_MAX_LENGTH}
              data-testid="tenant-group-rename-input"
              required
            />
          </label>
          {renameError || (renameName && renameValidation) ? (
            <Alert tone="error" className="mt-3">
              {renameError || renameValidation}
            </Alert>
          ) : null}
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(groupToDelete)}
        onOpenChange={(open) => !open && setGroupToDelete(null)}
        title={t('tenantManagement.groups.deleteDialog.title')}
        description={
          groupToDelete
            ? t('tenantManagement.groups.deleteDialog.description', { name: groupToDelete.name })
            : undefined
        }
        confirmLabel={deleting ? t('tenantManagement.groups.deleteDialog.deleting') : t('common.delete')}
        onConfirm={() => void handleDelete()}
      />

      <Modal
        open={Boolean(groupForRoles)}
        onOpenChange={(open) => !open && closeRoles()}
        title={t('tenantManagement.groups.rolesDialog.title')}
        footer={
          <>
            <span role="status" className="mr-auto">
              {rolesDirty ? (
                <Pill tone="warning" data-testid="tenant-group-roles-unsaved">
                  {t('tenantManagement.groups.rolesDialog.unsaved')}
                </Pill>
              ) : null}
            </span>
            <Button
              type="button"
              variant="pill-cancel"
              size="pill"
              onClick={closeRoles}
              data-testid="tenant-group-roles-cancel"
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="button"
              variant="pill-dark"
              size="pill"
              disabled={!rolesDirty || savingRoles}
              onClick={() => void handleSaveRoles()}
              data-testid="tenant-group-roles-save"
            >
              {savingRoles ? t('tenantManagement.saving') : t('tenantManagement.save')}
            </Button>
          </>
        }
      >
        <p className="text-[13.5px] text-muted-foreground">
          {t('tenantManagement.groups.rolesDialog.hint', { name: groupForRoles?.name ?? '' })}
        </p>
        <div className="mt-3 flex flex-col gap-1">
          {TENANT_ROLES.map((role) => (
            <CheckboxField
              key={role}
              label={role}
              checked={roleSelection.includes(role)}
              disabled={savingRoles}
              onCheckedChange={() => toggleRole(role)}
              data-testid={`tenant-group-role-checkbox-${groupForRoles?.name ?? 'unknown'}-${role}`}
            />
          ))}
        </div>
        {rolesError ? (
          <Alert tone="error" className="mt-3">
            {rolesError}
          </Alert>
        ) : null}
      </Modal>
    </>
  );
}

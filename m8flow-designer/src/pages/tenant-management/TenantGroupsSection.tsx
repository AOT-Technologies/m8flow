import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { FolderPlus, Pencil, Shield, Trash2 } from 'lucide-react';

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

export default function TenantGroupsSection({
  tenantId,
  existingGroupNames,
  reloadKey,
  onChanged,
}: TenantGroupsSectionProps) {
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [groups, setGroups] = useState<TenantGroup[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [groupToRename, setGroupToRename] = useState<TenantGroup | null>(null);
  const [renameName, setRenameName] = useState('');
  const [renameError, setRenameError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);

  const [groupToDelete, setGroupToDelete] = useState<TenantGroup | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [groupForRoles, setGroupForRoles] = useState<TenantGroup | null>(null);
  const [rolesError, setRolesError] = useState<string | null>(null);

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
          setError(tenantAdminErrorMessage(err, 'Failed to load groups'));
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

  const createValidation = useMemo(() => {
    const formatError = validateTenantGroupName(createName);
    if (formatError) {
      return formatError;
    }
    if (nameTaken(createName, existingGroupNames)) {
      return `Group '${normalizeTenantGroupName(createName)}' already exists in this tenant.`;
    }
    return null;
  }, [createName, existingGroupNames]);

  const renameValidation = useMemo(() => {
    const formatError = validateTenantGroupName(renameName);
    if (formatError) {
      return formatError;
    }
    if (groupToRename && nameTaken(renameName, existingGroupNames, groupToRename.name)) {
      return `Group '${normalizeTenantGroupName(renameName)}' already exists in this tenant.`;
    }
    return null;
  }, [renameName, existingGroupNames, groupToRename]);

  function openCreate() {
    setCreateName('');
    setCreateError(null);
    setCreateOpen(true);
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
      setCreateError(`Group '${normalized}' already exists in this tenant.`);
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await createTenantGroup(tenantId, normalized);
      setCreateOpen(false);
      onChanged();
    } catch (err: unknown) {
      setCreateError(tenantAdminErrorMessage(err, 'Failed to create group'));
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
      setRenameError(`Group '${normalized}' already exists in this tenant.`);
      return;
    }
    setRenaming(true);
    setRenameError(null);
    try {
      await renameTenantGroup(tenantId, groupToRename.name, normalized);
      setGroupToRename(null);
      onChanged();
    } catch (err: unknown) {
      setRenameError(tenantAdminErrorMessage(err, 'Failed to rename group'));
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
      setError(tenantAdminErrorMessage(err, 'Failed to delete group'));
      setGroupToDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  function openRoles(group: TenantGroup) {
    setGroupForRoles(group);
    setRolesError(null);
  }

  async function toggleRole(role: TenantRole) {
    if (!groupForRoles) {
      return;
    }
    const hasRole = groupForRoles.mapped_roles.includes(role);
    setRolesError(null);
    try {
      const payload = hasRole
        ? await revokeTenantGroupRole(tenantId, groupForRoles.name, role)
        : await grantTenantGroupRole(tenantId, groupForRoles.name, role);
      setGroupForRoles(payload.group);
      onChanged();
    } catch (err: unknown) {
      setRolesError(tenantAdminErrorMessage(err, 'Failed to update group roles'));
    }
  }

  const columns: DataTableColumn<TenantGroup>[] = [
    {
      key: 'name',
      header: 'Group',
      width: 'minmax(140px,1.4fr)',
      render: (group) => (
        <span className="font-medium text-foreground" data-testid={`tenant-group-name-cell-${group.id}`}>
          {group.name}
        </span>
      ),
    },
    {
      key: 'roles',
      header: 'Roles',
      width: 'minmax(160px,1.6fr)',
      render: (group) => (
        <div className="flex flex-wrap gap-1">
          {group.mapped_roles.length === 0 ? (
            <span className="text-muted-foreground">None</span>
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
      header: <span className="sr-only">Actions</span>,
      className: 'text-right whitespace-nowrap',
      width: 'minmax(220px,1fr)',
      render: (group) => (
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => openRename(group)}
            data-testid={`tenant-group-rename-button-${group.name}`}
          >
            <Pencil className="size-3.5" aria-hidden />
            Rename
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => openRoles(group)}
            data-testid={`tenant-group-manage-roles-button-${group.name}`}
          >
            <Shield className="size-3.5" aria-hidden />
            Roles
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setGroupToDelete(group)}
            data-testid={`tenant-group-remove-button-${group.name}`}
          >
            <Trash2 className="size-3.5" aria-hidden />
            Delete
          </Button>
        </>
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

      <Card variant="bordered" className="overflow-hidden">
        <div
          className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-[22px] py-3"
          data-testid="tenant-groups-toolbar"
        >
          <SearchBar
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Search groups…"
            aria-label="Search groups"
            data-testid="tenant-group-search-input"
            className="min-w-0 flex-1"
          />
          <Button
            type="button"
            variant="pill-dark"
            size="pill"
            onClick={openCreate}
            data-testid="tenant-group-add-button"
          >
            <FolderPlus className="size-3.5" aria-hidden />
            Add Group
          </Button>
        </div>

        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">Loading groups…</p>
        ) : groups.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">
            {search ? 'No groups match this search.' : 'No groups in this tenant yet.'}
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
        title="Add group"
        footer={
          <>
            <Button type="button" variant="pill-cancel" size="pill" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="tenant-group-create-form"
              variant="pill-dark"
              size="pill"
              disabled={creating || Boolean(createValidation)}
              data-testid="tenant-group-submit-button"
            >
              {creating ? 'Creating…' : 'Create'}
            </Button>
          </>
        }
      >
        <form id="tenant-group-create-form" onSubmit={(event) => void handleCreate(event)}>
          <p className="text-[13.5px] text-muted-foreground">
            People stay in the tenant if you later delete the group. Roles come from
            the group, not from a separate member-role editor.
          </p>
          <label className="mt-4 block text-sm font-medium text-foreground">
            Group name
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
        title="Rename group"
        footer={
          <>
            <Button
              type="button"
              variant="pill-cancel"
              size="pill"
              onClick={() => setGroupToRename(null)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              form="tenant-group-rename-form"
              variant="pill-dark"
              size="pill"
              disabled={renaming || Boolean(renameValidation)}
              data-testid="tenant-group-rename-submit-button"
            >
              {renaming ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <form id="tenant-group-rename-form" onSubmit={(event) => void handleRename(event)}>
          <p className="text-[13.5px] text-muted-foreground">
            Members stay in the group. The name must match the API rules.
          </p>
          <label className="mt-4 block text-sm font-medium text-foreground">
            Group name
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
        title="Delete group"
        description={
          groupToDelete
            ? `Delete ${groupToDelete.name}? People stay in the tenant. Roles that came only from this group go away.`
            : undefined
        }
        confirmLabel={deleting ? 'Deleting…' : 'Delete'}
        onConfirm={() => void handleDelete()}
      />

      <Modal
        open={Boolean(groupForRoles)}
        onOpenChange={(open) => !open && setGroupForRoles(null)}
        title="Group roles"
        footer={
          <Button
            type="button"
            variant="pill-cancel"
            size="pill"
            onClick={() => setGroupForRoles(null)}
          >
            Close
          </Button>
        }
      >
        <p className="text-[13.5px] text-muted-foreground">
          Members of {groupForRoles?.name} get these as effective roles. A group may
          map more than one role.
        </p>
        <div className="mt-3 flex flex-col gap-1">
          {TENANT_ROLES.map((role) => (
            <CheckboxField
              key={role}
              label={role}
              checked={groupForRoles?.mapped_roles.includes(role) ?? false}
              onCheckedChange={() => void toggleRole(role)}
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

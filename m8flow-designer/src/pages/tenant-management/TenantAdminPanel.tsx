import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MailPlus, Pencil, Plus, UserPlus, Users } from 'lucide-react';

import { Alert } from '@/components/library/alert/Alert';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { CheckboxField } from '@/components/library/checkbox-field/CheckboxField';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Pill } from '@/components/library/pill/Pill';
import { RadioGroupField } from '@/components/library/radio-group-field/RadioGroupField';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { WizardModal, type WizardModalStep } from '@/components/library/wizard-modal/WizardModal';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  addTenantGroupMember,
  addTenantMember,
  fetchAvailableTenantUsers,
  fetchTenantGroups,
  fetchTenantMembers,
  removeTenantGroupMember,
  removeTenantMember,
  tenantAdminErrorMessage,
  type TenantAvailableUser,
  type TenantGroup,
  type TenantMember,
} from '@/lib/tenantAdminApi';
import TenantGroupsSection from './TenantGroupsSection';
import InvitationManagementSection from './InvitationManagementSection';
import {
  MAX_TENANT_NAME_LENGTH,
  tenantsErrorMessage,
  updateTenantName,
  validateTenantDisplayName,
  type TenantStatus,
} from '@/lib/tenantsApi';

const MEMBERS_PAGE_SIZE = 10;
const PICKER_GROUPS_LIMIT = 100;
const AVAILABLE_USERS_PAGE_SIZE = 10;
const SEARCH_DEBOUNCE_MS = 300;

/** Mirrors `TenantsPage.tsx`'s own `STATUS_TONE` (kept local rather than
 * imported, since pages in this app don't otherwise import from each
 * other) — but keyed to `ui/badge.tsx`'s variant names rather than
 * `Pill`'s tone names (`destructive`, not `error`), since the header
 * reuses `Badge` to match the mockup's pill-shaped status chip. */
const STATUS_BADGE_VARIANT: Record<TenantStatus, 'success' | 'warning' | 'destructive'> = {
  ACTIVE: 'success',
  INACTIVE: 'warning',
  DELETED: 'destructive',
};

type TenantAdminTab = 'users' | 'groups' | 'invitations';

export type TenantAdminPanelProps = {
  tenantId: string;
  tenantName: string;
  /**
   * Alias/status for the header — carried from `TenantsPage`'s registry row
   * via router state (super-admin only; see `TenantManagementPage.tsx`).
   * `undefined` on the tenant-admin's own-tenant path: `/v1.0/m8flow/tenants`
   * is registry-scoped, so there's no second fetch to fall back to. The
   * header omits whichever piece it doesn't have rather than fabricating one.
   */
  tenantSlug?: string;
  tenantStatus?: TenantStatus;
  isSuperAdmin: boolean;
  refreshTenants?: () => void;
  onTenantNameChange?: (name: string) => void;
};

/** Adapter passed to `Breadcrumbs`' `LinkComponent` for client-side
 * navigation (component-adoption map, ticket 12). */
function RouterBreadcrumbLink({ href, className, children }: BreadcrumbLinkProps) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

/**
 * Members, groups, role grants, and (for super-admin) invitation management
 * for one tenant. Super-admin reaches this from the tenant registry; a
 * breadcrumb returns to `/tenants`. Does not set `m8flow_selected_tenant`.
 */
export default function TenantAdminPanel({
  tenantId,
  tenantName: initialTenantName,
  tenantSlug,
  tenantStatus,
  isSuperAdmin,
  refreshTenants,
  onTenantNameChange,
}: TenantAdminPanelProps) {
  const [tenantName, setTenantName] = useState(initialTenantName);
  const [tab, setTab] = useState<TenantAdminTab>('users');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [inviteOpen, setInviteOpen] = useState(false);
  // Live PENDING count reported by InvitationManagementSection — see its
  // own onCountChange doc comment. Starts at 0, not derived from `groups`
  // or `members`, since it tracks a status filter those don't have.
  const [pendingInvitationCount, setPendingInvitationCount] = useState(0);

  const [groups, setGroups] = useState<TenantGroup[]>([]);

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameName, setRenameName] = useState('');
  const [renameError, setRenameError] = useState<string | null>(null);
  const [savingName, setSavingName] = useState(false);

  const [addOpen, setAddOpen] = useState(false);
  const [availableUsers, setAvailableUsers] = useState<TenantAvailableUser[]>([]);
  const [availableSearch, setAvailableSearch] = useState('');
  const [availableOffset, setAvailableOffset] = useState(0);
  const [availableHasMore, setAvailableHasMore] = useState(false);
  const [loadingAvailable, setLoadingAvailable] = useState(false);
  const [selectedUsername, setSelectedUsername] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<TenantAvailableUser | null>(null);
  const [addGroupNames, setAddGroupNames] = useState<string[]>([]);
  const [addGroupFilter, setAddGroupFilter] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [memberToRemove, setMemberToRemove] = useState<TenantMember | null>(null);
  const [removing, setRemoving] = useState(false);

  const [memberForGroups, setMemberForGroups] = useState<TenantMember | null>(null);
  const [groupSelection, setGroupSelection] = useState<Set<string>>(new Set());
  const [savingGroups, setSavingGroups] = useState(false);
  const [groupsError, setGroupsError] = useState<string | null>(null);

  const skipSearchDebounce = useRef(true);

  useEffect(() => {
    setTenantName(initialTenantName);
  }, [initialTenantName]);

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
    fetchTenantMembers(tenantId, {
      search,
      offset: page * MEMBERS_PAGE_SIZE,
      limit: MEMBERS_PAGE_SIZE,
    })
      .then((payload) => {
        if (!cancelled) {
          setMembers(payload.members);
          setHasMore(payload.has_more);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(tenantAdminErrorMessage(err, 'Failed to load members'));
          setMembers([]);
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

  useEffect(() => {
    let cancelled = false;
    fetchTenantGroups(tenantId, { limit: PICKER_GROUPS_LIMIT })
      .then((payload) => {
        if (!cancelled) {
          setGroups(payload.groups);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGroups([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, reloadKey]);

  useEffect(() => {
    if (!addOpen || !tenantId) {
      return undefined;
    }
    let cancelled = false;
    setLoadingAvailable(true);
    fetchAvailableTenantUsers(tenantId, {
      search: availableSearch.trim(),
      offset: availableOffset,
      limit: AVAILABLE_USERS_PAGE_SIZE,
    })
      .then((payload) => {
        if (!cancelled) {
          setAvailableUsers(payload.users);
          setAvailableHasMore(payload.has_more);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setAddError(tenantAdminErrorMessage(err, 'Failed to load available users'));
          setAvailableUsers([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingAvailable(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [addOpen, tenantId, availableSearch, availableOffset]);

  const groupNames = useMemo(() => groups.map((group) => group.name), [groups]);
  const filteredAddGroupNames = useMemo(() => {
    const term = addGroupFilter.trim().toLowerCase();
    if (!term) {
      return groupNames;
    }
    return groupNames.filter((name) => name.toLowerCase().includes(term));
  }, [groupNames, addGroupFilter]);

  function openRename() {
    setRenameName(tenantName);
    setRenameError(null);
    setRenameOpen(true);
  }

  async function handleRename(event: FormEvent) {
    event.preventDefault();
    if (!tenantId || savingName) {
      return;
    }
    const trimmed = renameName.trim();
    const nameError = validateTenantDisplayName(trimmed);
    if (nameError) {
      setRenameError(nameError);
      return;
    }
    setSavingName(true);
    setRenameError(null);
    try {
      await updateTenantName(tenantId, trimmed);
      setTenantName(trimmed);
      setRenameOpen(false);
      onTenantNameChange?.(trimmed);
      refreshTenants?.();
    } catch (err: unknown) {
      setRenameError(tenantsErrorMessage(err, 'Failed to rename tenant'));
    } finally {
      setSavingName(false);
    }
  }

  function openAdd() {
    setAddOpen(true);
    setAvailableSearch('');
    setAvailableOffset(0);
    setSelectedUsername(null);
    setSelectedUser(null);
    setAddGroupNames([]);
    setAddGroupFilter('');
    setAddError(null);
  }

  function selectAvailableUser(username: string) {
    setSelectedUsername(username);
    setSelectedUser(availableUsers.find((user) => user.username === username) ?? null);
  }

  function toggleAddGroup(name: string) {
    setAddGroupNames((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
  }

  async function handleAdd() {
    if (!tenantId || !selectedUsername || adding) {
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      await addTenantMember(tenantId, {
        username: selectedUsername,
        group_names: addGroupNames.length > 0 ? addGroupNames : undefined,
      });
      setAddOpen(false);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setAddError(tenantAdminErrorMessage(err, 'Failed to add member'));
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove() {
    if (!tenantId || !memberToRemove || removing) {
      return;
    }
    setRemoving(true);
    setError(null);
    try {
      await removeTenantMember(tenantId, memberToRemove.username);
      setMemberToRemove(null);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setError(tenantAdminErrorMessage(err, 'Failed to remove member'));
      setMemberToRemove(null);
    } finally {
      setRemoving(false);
    }
  }

  function openManageGroups(member: TenantMember) {
    setMemberForGroups(member);
    setGroupSelection(new Set(member.groups.map((group) => group.name)));
    setGroupsError(null);
  }

  function toggleGroupSelection(name: string) {
    setGroupSelection((current) => {
      const next = new Set(current);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  async function handleSaveGroups() {
    if (!tenantId || !memberForGroups || savingGroups) {
      return;
    }
    const current = new Set(memberForGroups.groups.map((group) => group.name));
    const toAdd = [...groupSelection].filter((name) => !current.has(name));
    const toRemove = [...current].filter((name) => !groupSelection.has(name));
    setSavingGroups(true);
    setGroupsError(null);
    try {
      await Promise.all([
        ...toAdd.map((name) => addTenantGroupMember(tenantId, name, memberForGroups.username)),
        ...toRemove.map((name) =>
          removeTenantGroupMember(tenantId, name, memberForGroups.username),
        ),
      ]);
      setMemberForGroups(null);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setGroupsError(tenantAdminErrorMessage(err, 'Failed to update groups'));
    } finally {
      setSavingGroups(false);
    }
  }

  const memberColumns: DataTableColumn<TenantMember>[] = [
    {
      key: 'member',
      header: 'Member',
      width: 'minmax(160px,1.4fr)',
      render: (member) => (
        <div>
          <div className="font-medium text-foreground">
            {member.display_name || member.username}
          </div>
          <div className="text-[13px] text-muted-foreground">{member.username}</div>
        </div>
      ),
    },
    {
      key: 'roles',
      header: 'Effective roles',
      width: 'minmax(140px,1.2fr)',
      render: (member) => (
        <div className="flex flex-wrap gap-1">
          {member.roles.length === 0 ? (
            <span className="text-muted-foreground">None</span>
          ) : (
            member.roles.map((role) => (
              <Pill
                key={role}
                tone="info"
                dot={false}
                data-testid={`tenant-member-role-chip-${member.username}-${role}`}
              >
                {role}
              </Pill>
            ))
          )}
        </div>
      ),
    },
    {
      key: 'groups',
      header: 'Groups',
      width: 'minmax(140px,1.2fr)',
      render: (member) => (
        <div className="flex flex-wrap gap-1">
          {member.groups.length === 0 ? (
            <span className="text-muted-foreground">None</span>
          ) : (
            member.groups.map((group) => (
              <Badge
                key={group.id || group.name}
                variant="outline"
                data-testid={`tenant-member-group-chip-${member.username}-${group.name}`}
              >
                {group.name}
              </Badge>
            ))
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      className: 'text-right whitespace-nowrap',
      width: 'minmax(180px,1fr)',
      render: (member) => (
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => openManageGroups(member)}
            data-testid={`tenant-member-manage-groups-button-${member.username}`}
          >
            <Users className="size-3.5" aria-hidden />
            Groups
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setMemberToRemove(member)}
            data-testid={`tenant-member-remove-button-${member.username}`}
          >
            Remove
          </Button>
        </>
      ),
    },
  ];

  const addMemberSteps: WizardModalStep[] = [
    {
      title: 'Add Member',
      canContinue: Boolean(selectedUsername),
      continueTestId: 'tenant-member-add-next',
      body: (
        <>
          <p className="mb-3 text-[13.5px] text-muted-foreground">
            Pick an existing shared-realm user. This is not an email invitation.
          </p>
          <SearchBar
            variant="sunken"
            value={availableSearch}
            onChange={(value) => {
              setAvailableSearch(value);
              setAvailableOffset(0);
            }}
            placeholder="Search available users…"
            aria-label="Search available users"
          />
          {loadingAvailable ? (
            <p className="mt-3 px-3 py-3 text-sm text-muted-foreground">Loading users…</p>
          ) : availableUsers.length === 0 ? (
            <p className="mt-3 px-3 py-3 text-sm text-muted-foreground">No available users.</p>
          ) : (
            <RadioGroupField
              className="mt-3 flex max-h-72 flex-col items-stretch gap-0 overflow-y-auto rounded-lg border border-border"
              optionClassName="w-full px-3 py-2 hover:bg-muted"
              options={availableUsers.map((user) => ({
                value: user.username,
                label: (
                  <span>
                    <span className="font-medium">{user.display_name || user.username}</span>
                    <span className="ml-2 text-muted-foreground">{user.username}</span>
                  </span>
                ),
              }))}
              value={selectedUsername ?? ''}
              onValueChange={selectAvailableUser}
            />
          )}
          {availableHasMore || availableOffset > 0 ? (
            <div className="mt-2 flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={availableOffset === 0}
                onClick={() =>
                  setAvailableOffset((current) => Math.max(0, current - AVAILABLE_USERS_PAGE_SIZE))
                }
              >
                Previous
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={!availableHasMore}
                onClick={() => setAvailableOffset((current) => current + AVAILABLE_USERS_PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          ) : null}
          {addError ? (
            <Alert tone="error" className="mt-3">
              {addError}
            </Alert>
          ) : null}
        </>
      ),
    },
    {
      title: 'Add Member',
      canContinue: Boolean(selectedUsername) && !adding,
      continueLabel: (
        <>
          <Plus className="size-3.5" aria-hidden />
          {adding ? 'Adding…' : 'Add'}
        </>
      ),
      continueTestId: 'tenant-member-add-submit',
      body: (
        <>
          <p className="mb-3 text-[13.5px] text-muted-foreground">
            Choose which groups to add this member to.
          </p>
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <span className="text-sm">
              <span className="font-medium">{selectedUser?.display_name || selectedUsername}</span>
              <span className="ml-2 text-muted-foreground">{selectedUsername}</span>
            </span>
          </div>
          {groupNames.length > 0 ? (
            <fieldset className="mt-4">
              <legend className="text-sm font-medium">Groups (optional)</legend>
              {groupNames.length > 8 ? (
                <div className="mt-2">
                  <SearchBar
                    variant="sunken"
                    value={addGroupFilter}
                    onChange={setAddGroupFilter}
                    placeholder="Filter groups…"
                    aria-label="Filter groups"
                  />
                </div>
              ) : null}
              <div className="mt-2 flex max-h-72 flex-col gap-1 overflow-y-auto rounded-lg border border-border p-2">
                {filteredAddGroupNames.length === 0 ? (
                  <p className="px-1 py-1 text-sm text-muted-foreground">No matching groups.</p>
                ) : (
                  filteredAddGroupNames.map((name) => (
                    <CheckboxField
                      key={name}
                      label={name}
                      containerClassName="rounded px-1 py-1 hover:bg-muted"
                      checked={addGroupNames.includes(name)}
                      onCheckedChange={() => toggleAddGroup(name)}
                      data-testid={`tenant-add-member-group-${name}`}
                    />
                  ))
                )}
              </div>
            </fieldset>
          ) : null}
          {addError ? (
            <Alert tone="error" className="mt-3">
              {addError}
            </Alert>
          ) : null}
        </>
      ),
    },
  ];

  const tenantInitial = (tenantName || tenantId).trim().charAt(0).toUpperCase() || '?';

  return (
    <main className="flex-1 px-11 py-10">
      {isSuperAdmin ? (
        <Breadcrumbs
          className="mb-4 text-[13.5px] text-muted-foreground"
          LinkComponent={RouterBreadcrumbLink}
          linkClassName="shrink-0 text-info font-semibold"
          items={[
            { label: 'Tenants', href: '/tenants' },
            { label: tenantName || tenantId },
          ]}
        />
      ) : null}

      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div
            className="flex size-11 shrink-0 items-center justify-center rounded-[10px] bg-info/10 font-display text-lg font-bold text-info"
            aria-hidden
          >
            {tenantInitial}
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="font-display text-[28px] font-semibold tracking-tight text-foreground">
                {tenantName || tenantId}
              </h1>
              {tenantStatus ? (
                <Badge variant={STATUS_BADGE_VARIANT[tenantStatus]} data-testid="tenant-management-status-badge">
                  {tenantStatus}
                </Badge>
              ) : null}
            </div>
            <div className="mt-0.5 font-mono text-[12.5px] text-muted-foreground">
              {tenantSlug || tenantId}
            </div>
          </div>
        </div>
        <Button
          type="button"
          variant="pill-outline"
          size="pill"
          onClick={openRename}
          data-testid="tenant-management-edit-button"
        >
          <Pencil className="size-3.5" aria-hidden />
          Edit Tenant
        </Button>
      </div>

      {/* Tabs/TabsList/TabsTrigger only — no TabsContent. Same pattern as
          ProcessInstanceDetailPage: panels below are plain `tab === 'x'`
          conditionals, not Radix's own tabpanel, because Radix unmounts an
          inactive TabsContent's children by default (no `forceMount`),
          which would zero out the Invitations panel's own live PENDING
          count every time the user left that tab. The Invitations panel
          below stays mounted (CSS-`hidden`, not conditionally rendered) for
          the same reason — its fetch needs to run before it's ever opened,
          so the tab's own count badge is right from first paint, not just
          after a visit. Users/Groups have no such requirement (their badge
          counts come from state already fetched at this level, not from
          the panel component itself), so those two use the plain unmount-
          on-switch conditional like the rest of the app. */}
      <Tabs value={tab} onValueChange={(value) => setTab(value as TenantAdminTab)}>
        <TabsList className="mb-5 gap-7">
          <TabsTrigger value="users" className="gap-1.5">
            Users
            <Badge variant="secondary">{hasMore ? `${members.length}+` : members.length}</Badge>
          </TabsTrigger>
          <TabsTrigger value="groups" className="gap-1.5">
            Groups
            <Badge variant="secondary">{groups.length}</Badge>
          </TabsTrigger>
          {isSuperAdmin ? (
            <TabsTrigger value="invitations" className="gap-1.5">
              Pending invites
              <Badge variant="secondary">{pendingInvitationCount}</Badge>
            </TabsTrigger>
          ) : null}
        </TabsList>
      </Tabs>

      {tab === 'users' ? (
        <>
          {error ? (
            <Alert tone="error" className="mb-4">
              {error}
            </Alert>
          ) : null}

          <Card variant="bordered" className="overflow-hidden">
            <div
              className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-[22px] py-3"
              data-testid="tenant-members-toolbar"
            >
              <SearchBar
                value={searchInput}
                onChange={setSearchInput}
                placeholder="Search tenant members…"
                aria-label="Search tenant members"
                data-testid="tenant-member-search-input"
                className="min-w-0 flex-1"
              />
              <div className="flex flex-wrap items-center gap-2">
                {isSuperAdmin ? (
                  <Button
                    type="button"
                    variant="pill-outline"
                    size="pill"
                    onClick={() => setInviteOpen(true)}
                    data-testid="tenant-invite-user-button"
                  >
                    <MailPlus className="size-3.5" aria-hidden />
                    Invite User
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="pill-dark"
                  size="pill"
                  onClick={openAdd}
                  data-testid="tenant-member-add-button"
                >
                  <UserPlus className="size-3.5" aria-hidden />
                  Add Member
                </Button>
              </div>
            </div>

            {loading ? (
              <p className="px-[22px] py-6 text-sm text-muted-foreground">Loading members…</p>
            ) : members.length === 0 ? (
              <p className="px-[22px] py-6 text-sm text-muted-foreground">
                {search ? 'No members match this search.' : 'No members in this tenant yet.'}
              </p>
            ) : (
              <DataTable
                columns={memberColumns}
                rows={members}
                getRowKey={(member) => member.username}
                data-testid="tenant-member-table-container"
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
        </>
      ) : null}

      {tab === 'groups' && tenantId ? (
        <TenantGroupsSection
          tenantId={tenantId}
          existingGroupNames={groupNames}
          reloadKey={reloadKey}
          onChanged={() => setReloadKey((key) => key + 1)}
        />
      ) : null}

      {isSuperAdmin && tenantId ? (
        <div className={tab === 'invitations' ? undefined : 'hidden'}>
          <div className="mb-3 flex justify-end">
            <Button
              type="button"
              variant="pill-dark"
              size="pill"
              onClick={() => setInviteOpen(true)}
              data-testid="tenant-invite-user-button-invitations-tab"
            >
              <MailPlus className="size-3.5" aria-hidden />
              Invite User
            </Button>
          </div>
          <InvitationManagementSection
            tenantId={tenantId}
            inviteOpen={inviteOpen}
            onInviteOpenChange={setInviteOpen}
            onCountChange={setPendingInvitationCount}
          />
        </div>
      ) : null}

      <Modal
        open={renameOpen}
        onOpenChange={setRenameOpen}
        title="Edit Tenant"
        footer={
          <>
            <Button type="button" variant="pill-cancel" size="pill" onClick={() => setRenameOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="tenant-rename-form"
              variant="pill-dark"
              size="pill"
              disabled={!renameName.trim() || savingName}
              data-testid="tenant-save"
            >
              {savingName ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <form id="tenant-rename-form" onSubmit={(event) => void handleRename(event)}>
          <p className="text-[13.5px] text-muted-foreground">
            The alias stays the same. Only the display name changes.
          </p>
          <label className="mt-4 block text-sm font-medium text-foreground">
            Tenant name
            <Input
              className="mt-1.5"
              value={renameName}
              onChange={(event) => setRenameName(event.target.value)}
              autoComplete="off"
              maxLength={MAX_TENANT_NAME_LENGTH}
              data-testid="tenant-name"
              required
            />
          </label>
          {renameError ? (
            <Alert tone="error" className="mt-3">
              {renameError}
            </Alert>
          ) : null}
        </form>
      </Modal>

      <WizardModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onComplete={() => void handleAdd()}
        steps={addMemberSteps}
        size="md"
      />

      <ConfirmDialog
        open={Boolean(memberToRemove)}
        onOpenChange={(open) => !open && setMemberToRemove(null)}
        title="Remove member"
        description={
          memberToRemove
            ? `Remove ${memberToRemove.display_name || memberToRemove.username} from this tenant? They will lose group memberships here.`
            : undefined
        }
        confirmLabel={removing ? 'Removing…' : 'Remove'}
        onConfirm={() => void handleRemove()}
      />

      <Modal
        open={Boolean(memberForGroups)}
        onOpenChange={(open) => !open && setMemberForGroups(null)}
        title="Member groups"
        footer={
          <>
            <Button
              type="button"
              variant="pill-cancel"
              size="pill"
              onClick={() => setMemberForGroups(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="pill-dark"
              size="pill"
              disabled={savingGroups}
              onClick={() => void handleSaveGroups()}
              data-testid="tenant-member-groups-save"
            >
              {savingGroups ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <p className="text-[13.5px] text-muted-foreground">
          Effective roles come from these groups. There is no separate member-role
          editor.
        </p>
        <div className="mt-3 flex flex-col gap-1">
          {groups.length === 0 ? (
            <p className="text-sm text-muted-foreground">No groups in this tenant yet.</p>
          ) : (
            groups.map((group) => (
              <CheckboxField
                key={group.id || group.name}
                label={group.name}
                checked={groupSelection.has(group.name)}
                onCheckedChange={() => toggleGroupSelection(group.name)}
                data-testid={`tenant-member-group-toggle-${group.name}`}
              />
            ))
          )}
        </div>
        {groupsError ? (
          <Alert tone="error" className="mt-3">
            {groupsError}
          </Alert>
        ) : null}
      </Modal>
    </main>
  );
}

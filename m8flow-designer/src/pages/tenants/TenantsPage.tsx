import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDown, ArrowUp, Building2, Plus } from 'lucide-react';

import { useActiveTenant, useTenantRegistry } from '@/components/session/hooks';
import { Alert } from '@/components/library/alert/Alert';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pill, type PillProps } from '@/components/library/pill/Pill';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { SortDropdown } from '@/components/library/sort-dropdown/SortDropdown';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  createTenant,
  fetchTenants,
  generateUniqueTenantAlias,
  isDuplicateTenantName,
  MAX_TENANT_NAME_LENGTH,
  tenantsErrorMessage,
  validateTenantDisplayName,
  type Tenant,
  type TenantStatus,
} from '@/lib/tenantsApi';
import { cn } from '@/lib/utils';

type SearchField = 'name' | 'slug';
type SortField = 'name' | 'slug';
type SortDirection = 'asc' | 'desc';
type StatusFilter = 'all' | 'ACTIVE' | 'INACTIVE';

const STATUS_TONE: Record<TenantStatus, NonNullable<PillProps['tone']>> = {
  ACTIVE: 'success',
  INACTIVE: 'warning',
  DELETED: 'error',
};

const SEARCH_FIELD_OPTIONS = [
  { label: 'Tenant name', value: 'name' },
  { label: 'Tenant alias', value: 'slug' },
];

const STATUS_FILTER_OPTIONS = [
  { label: 'Any status', value: 'all' },
  { label: 'Active', value: 'ACTIVE' },
  { label: 'Inactive', value: 'INACTIVE' },
];

/**
 * Super-admin tenant registry. List / search / sort / status filter / create.
 * Selecting a tenant opens tenant admin for that tenant.
 * Does not set `m8flow_selected_tenant`, mutate status, or delete.
 */
export default function TenantsPage() {
  const { isSuperAdmin } = useActiveTenant();
  const { refreshTenants } = useTenantRegistry();

  const [rows, setRows] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(isSuperAdmin);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchField, setSearchField] = useState<SearchField>('name');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sortField, setSortField] = useState<SortField>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  const [createOpen, setCreateOpen] = useState(false);
  const [dialogName, setDialogName] = useState('');
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isSuperAdmin) {
      setRows([]);
      setLoading(false);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTenants()
      .then((payload) => {
        if (!cancelled) {
          setRows(payload);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(tenantsErrorMessage(err, 'Failed to load tenants'));
          setRows([]);
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
  }, [isSuperAdmin, reloadKey]);

  const visible = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    let filtered = rows;
    if (query) {
      filtered = filtered.filter((tenant) =>
        searchField === 'name'
          ? tenant.name.toLowerCase().includes(query)
          : tenant.slug.toLowerCase().includes(query),
      );
    }
    if (statusFilter !== 'all') {
      filtered = filtered.filter((tenant) => tenant.status === statusFilter);
    }
    return [...filtered].sort((a, b) => {
      const left = a[sortField].toLowerCase();
      const right = b[sortField].toLowerCase();
      const compared = left.localeCompare(right);
      return sortDirection === 'asc' ? compared : -compared;
    });
  }, [rows, searchQuery, searchField, statusFilter, sortField, sortDirection]);

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortField(field);
    setSortDirection('asc');
  }

  function openCreate() {
    setCreateOpen(true);
    setDialogName('');
    setDialogError(null);
  }

  function closeDialog() {
    if (saving) {
      return;
    }
    setCreateOpen(false);
    setDialogName('');
    setDialogError(null);
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!createOpen || saving) {
      return;
    }
    const trimmed = dialogName.trim();
    const nameError = validateTenantDisplayName(trimmed);
    if (nameError) {
      setDialogError(nameError);
      return;
    }
    if (isDuplicateTenantName(trimmed, rows)) {
      setDialogError('A tenant with this name already exists.');
      return;
    }

    setSaving(true);
    setDialogError(null);
    try {
      await createTenant(trimmed, rows);
      setCreateOpen(false);
      setDialogName('');
      setReloadKey((key) => key + 1);
      refreshTenants();
    } catch (err: unknown) {
      setDialogError(tenantsErrorMessage(err, 'Failed to create tenant'));
    } finally {
      setSaving(false);
    }
  }

  if (!isSuperAdmin) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">Tenants</h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">Not available</p>
          <p className="mt-2 text-sm text-muted-foreground">
            The tenant registry is for platform admins. Your role cannot list or manage
            tenants.
          </p>
        </Card>
      </main>
    );
  }

  const columns: DataTableColumn<Tenant>[] = [
    {
      key: 'name',
      header: (
        <SortHeader
          label="Tenant name"
          field="name"
          active={sortField}
          direction={sortDirection}
          onToggle={toggleSort}
        />
      ),
      width: 'minmax(160px,1.6fr)',
      render: (tenant) => (
        <Link
          to={`/tenant-management/${encodeURIComponent(tenant.id)}`}
          state={{ tenantName: tenant.name, tenantSlug: tenant.slug, tenantStatus: tenant.status }}
          className="text-left font-medium text-foreground no-underline hover:underline"
          data-testid={`tenant-open-${tenant.id}`}
        >
          {tenant.name}
        </Link>
      ),
    },
    {
      key: 'slug',
      header: (
        <SortHeader
          label="Tenant alias"
          field="slug"
          active={sortField}
          direction={sortDirection}
          onToggle={toggleSort}
        />
      ),
      width: 'minmax(120px,1fr)',
      render: (tenant) => (
        <span className="font-mono text-[13px] text-muted-foreground">{tenant.slug}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: 'minmax(90px,120px)',
      render: (tenant) => (
        <Pill tone={STATUS_TONE[tenant.status]} dot={false}>
          {tenant.status}
        </Pill>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      className: 'text-right whitespace-nowrap',
      width: 'minmax(90px,110px)',
      render: (tenant) => (
        <Button variant="ghost" size="sm" asChild>
          <Link
            to={`/tenant-management/${encodeURIComponent(tenant.id)}`}
            state={{ tenantName: tenant.name, tenantSlug: tenant.slug, tenantStatus: tenant.status }}
            data-testid={`tenant-manage-${tenant.id}`}
          >
            Manage
          </Link>
        </Button>
      ),
    },
  ];

  const searchPlaceholder =
    searchField === 'name' ? 'Search by tenant name' : 'Search by tenant alias';
  const emptyCopy =
    searchQuery.trim() || statusFilter !== 'all'
      ? 'No tenants found matching your filters'
      : 'No tenants available';

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[32px] font-semibold tracking-tight">Tenants</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Register the organizations that back access in Keycloak. Select a tenant
            to manage members, groups, roles, and invitations.
          </p>
        </div>
        <Button
          type="button"
          variant="pill-dark"
          size="pill"
          onClick={openCreate}
          data-testid="tenant-add-button"
        >
          <Plus className="size-3.5" aria-hidden />
          Add Tenant
        </Button>
      </div>

      <div className="mb-[18px] flex flex-wrap items-center gap-2.5">
        <SortDropdown
          label="Search by"
          options={SEARCH_FIELD_OPTIONS}
          value={searchField}
          onChange={(value) => setSearchField(value as SearchField)}
          className="min-w-0"
        />
        <SearchBar
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          data-testid="tenant-search-input"
          className="min-w-0 flex-1"
        />
        <SortDropdown
          label="Status"
          options={STATUS_FILTER_OPTIONS}
          value={statusFilter}
          onChange={(value) => setStatusFilter(value as StatusFilter)}
          className="min-w-0"
        />
        <div className="ml-auto whitespace-nowrap text-[13px] text-muted-foreground">
          {loading
            ? 'Loading…'
            : `Showing ${visible.length} of ${rows.length} tenant${rows.length === 1 ? '' : 's'}`}
        </div>
      </div>

      {error ? (
        <Alert tone="error" className="mb-4">
          {error}
        </Alert>
      ) : null}

      <Card variant="bordered" className="overflow-hidden">
        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">Loading tenants…</p>
        ) : visible.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">{emptyCopy}</p>
        ) : (
          <DataTable columns={columns} rows={visible} getRowKey={(tenant) => tenant.id} />
        )}
      </Card>

      <Modal
        open={createOpen}
        onOpenChange={(open) => !open && closeDialog()}
        title="Add Tenant"
        footer={
          <>
            <Button type="button" variant="pill-cancel" size="pill" onClick={closeDialog}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="tenant-create-form"
              variant="pill-dark"
              size="pill"
              disabled={!dialogName.trim() || saving}
              data-testid="tenant-save"
            >
              {saving ? 'Saving…' : 'Create'}
            </Button>
          </>
        }
      >
        <form id="tenant-create-form" onSubmit={(event) => void handleSave(event)}>
          <p className="text-[13.5px] text-muted-foreground">
            Give this organization a display name. The alias is generated from it.
          </p>
          <label className="mt-4 block text-sm font-medium text-foreground">
            Tenant name
            <Input
              className="mt-1.5"
              value={dialogName}
              onChange={(event) => setDialogName(event.target.value)}
              autoComplete="off"
              maxLength={MAX_TENANT_NAME_LENGTH}
              data-testid="tenant-name"
              required
            />
          </label>
          {dialogName.trim() ? (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Building2 className="size-3" aria-hidden />
              Alias: {generateUniqueTenantAlias(dialogName, rows)}
            </p>
          ) : null}
          {dialogError ? (
            <Alert tone="error" className="mt-3">
              {dialogError}
            </Alert>
          ) : null}
        </form>
      </Modal>
    </main>
  );
}

function SortHeader({
  label,
  field,
  active,
  direction,
  onToggle,
}: {
  label: string;
  field: SortField;
  active: SortField;
  direction: SortDirection;
  onToggle: (field: SortField) => void;
}) {
  const isActive = active === field;
  const Icon = isActive && direction === 'desc' ? ArrowDown : ArrowUp;
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center gap-1 tracking-[0.06em] uppercase',
        isActive ? 'text-foreground' : 'text-muted-foreground',
      )}
      onClick={() => onToggle(field)}
      aria-label={`Sort by ${label}, ${isActive ? direction : 'ascending'}`}
      data-testid={`tenant-sort-${field}`}
    >
      {label}
      <Icon className={cn('size-3', isActive ? 'opacity-100' : 'opacity-40')} aria-hidden />
    </button>
  );
}

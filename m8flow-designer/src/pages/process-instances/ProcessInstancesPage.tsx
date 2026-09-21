import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  fetchProcessInstanceOwners,
  fetchProcessInstances,
  type ProcessInstanceListItem,
  type ProcessInstancePagination,
  type ProcessInstanceSort,
} from '@/lib/processInstancesApi';
import { useActiveTenant } from '@/components/session/hooks';
import { ProcessInstancesList } from './components/ProcessInstancesList';

const PER_PAGE_DEFAULT = 25;
/** Same debounce rationale as TemplatesPage's own search box — this list
 * is server-paginated/-searched, so debouncing avoids a request per
 * keystroke. */
const SEARCH_DEBOUNCE_MS = 300;

/**
 * Process Instances list — wired to GET /v1.0/m8flow/process-instances
 * (Process Instances + task-state map, ticket 02 —
 * `.scratch/process-instances-task-state/`). Same tenant-gating posture as
 * Processes/Templates: super-admin must pick a concrete tenant, no merged
 * all-tenant catalog view.
 *
 * `?search=` seeds the initial search box (capstone ticket, read once on
 * mount, not kept in sync afterward — same one-way "deep link in, free
 * text out" convention `ProcessesPage`'s own `?group=` uses). Lets
 * `ProcessModelOverview`'s "View all N" link land here pre-filtered to
 * that process model's display name, without this page needing to know
 * anything about process models specifically.
 */
export default function ProcessInstancesPage() {
  const { scopedTenantId, isSuperAdmin } = useActiveTenant();
  // All Tenants (super-admin, no concrete tenant) renders the merged
  // cross-tenant list instead of a "choose a tenant" gate.
  const allTenants = isSuperAdmin && !scopedTenantId;
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const initialSearch = searchParams.get('search') ?? '';
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [search, setSearch] = useState(initialSearch);
  const [status, setStatus] = useState('');
  const [startedBy, setStartedBy] = useState('');
  const [sort, setSort] = useState<ProcessInstanceSort>('newest');
  const [perPage, setPerPage] = useState(PER_PAGE_DEFAULT);
  const [page, setPage] = useState(1);

  const [instances, setInstances] = useState<ProcessInstanceListItem[]>([]);
  const [pagination, setPagination] = useState<ProcessInstancePagination | null>(null);
  const [owners, setOwners] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Any filter/sort/page-size change resets to page 1 — a stale high page
  // number would otherwise show an empty result set until the user paged back.
  useEffect(() => {
    setPage(1);
  }, [status, startedBy, sort, perPage]);

  useEffect(() => {

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchProcessInstances({
      status: status || undefined,
      search: search || undefined,
      startedBy: startedBy || undefined,
      sort,
      page,
      perPage,
      tenantId: scopedTenantId ?? undefined,
    })
      .then(({ results, pagination: pg }) => {
        if (!cancelled) {
          setInstances(results);
          setPagination(pg);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load process instances');
          setInstances([]);
          setPagination(null);
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
  }, [scopedTenantId, search, status, startedBy, sort, page, perPage]);

  // Owner dropdown options — reloaded only when the tenant scope changes, not
  // on every filter/page change (the option set is tenant-wide, independent of
  // the current filters). Failures leave the dropdown at "All owners" only.
  useEffect(() => {
    let cancelled = false;
    fetchProcessInstanceOwners(scopedTenantId ?? undefined)
      .then((list) => {
        if (!cancelled) setOwners(list);
      })
      .catch(() => {
        if (!cancelled) setOwners([]);
      });
    return () => {
      cancelled = true;
    };
  }, [scopedTenantId]);

  return (
    <main className="flex-1 px-11 py-10">
      <ProcessInstancesList
        instances={instances}
        loading={loading}
        error={error}
        search={searchInput}
        onSearchChange={setSearchInput}
        status={status}
        onStatusChange={setStatus}
        owners={owners}
        startedBy={startedBy}
        onStartedByChange={setStartedBy}
        sort={sort}
        onSortChange={setSort}
        page={page}
        perPage={perPage}
        onPerPageChange={setPerPage}
        totalCount={pagination?.total ?? instances.length}
        onPageChange={setPage}
        showTenant={allTenants}
        onOpenInstance={(instance) => navigate(`/process-instances/${instance.id}`)}
      />
    </main>
  );
}

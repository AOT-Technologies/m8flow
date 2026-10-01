import { useEffect, useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useActiveTenant } from '@/components/session/hooks';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Pill } from '@/components/library/pill/Pill';
import { processInstanceStatusToPillProps } from '@/components/library/pill/processInstanceStatusToPillProps';
import { Card } from '@/components/ui/card';
import { formatRelativeTime } from '@/lib/relativeTime';
import {
  fetchTaskReviewList,
  type TaskReviewListItem,
  type TaskReviewPagination,
  type TaskReviewSort,
} from '@/lib/tasksApi';

const PER_PAGE = 20;
/** Tasks created within this window get a "New" pill. */
const NEW_TASK_WINDOW_SECONDS = 60 * 60;
/** Silent refetch so new tasks surface without a page refresh. */
const REFRESH_INTERVAL_MS = 30_000;

function isNewTask(task: TaskReviewListItem): boolean {
  return (
    task.created_at_in_seconds != null &&
    Date.now() / 1000 - task.created_at_in_seconds < NEW_TASK_WINDOW_SECONDS
  );
}

/**
 * Task Review — "My tasks" inbox. Wired to GET /v1.0/m8flow/task-review
 * (the caller's pending human tasks; super-admin sees every tenant's,
 * narrowable via the sidebar tenant selector). Rows open the review detail
 * at `/task-review/:taskId`. Same outlet-context tenant-scoping + fetch
 * state-machine as ProcessInstancesPage; super-admin is NOT forced to pick a
 * concrete tenant here (the backend returns all-tenant pending tasks).
 */
export default function TaskReviewInboxPage() {
  const { scopedTenantId, isSuperAdmin } = useActiveTenant();
  const navigate = useNavigate();

  const [tasks, setTasks] = useState<TaskReviewListItem[]>([]);
  const [pagination, setPagination] = useState<TaskReviewPagination | null>(null);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<TaskReviewSort>('newest');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const load = () =>
      fetchTaskReviewList({ page, perPage: PER_PAGE, tenantId: scopedTenantId ?? undefined, sort })
        .then(({ results, pagination: pg }) => {
          if (!cancelled) {
            setTasks(results);
            setPagination(pg);
            setError(null);
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : 'Failed to load tasks');
            setTasks([]);
            setPagination(null);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });

    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [scopedTenantId, page, sort]);

  const toggleSort = () => {
    setSort((current) => (current === 'newest' ? 'oldest' : 'newest'));
    setPage(1);
  };
  const SortIcon = sort === 'newest' ? ArrowDown : ArrowUp;

  const total = pagination?.total ?? tasks.length;

  const columns: DataTableColumn<TaskReviewListItem>[] = [
    {
      key: 'task',
      header: 'Task',
      width: 'minmax(200px,2fr)',
      className: 'font-medium text-foreground',
      render: (task) => (
        <span className="inline-flex items-center gap-2">
          {task.task_title || task.task_name}
          {isNewTask(task) ? (
            <Pill tone="info" dot={false}>
              New
            </Pill>
          ) : null}
        </span>
      ),
    },
    {
      key: 'process',
      header: 'Process',
      width: 'minmax(160px,1.2fr)',
      className: 'text-muted-foreground',
      render: (task) => task.process_model_display_name,
    },
    {
      key: 'submittedBy',
      header: 'Submitted by',
      width: 'minmax(0,140px)',
      className: 'text-muted-foreground',
      render: (task) => task.submitted_by ?? '—',
    },
    ...(isSuperAdmin
      ? [
          {
            key: 'tenant',
            header: 'Tenant',
            width: 'minmax(0,140px)',
            className: 'text-muted-foreground',
            render: (task: TaskReviewListItem) => task.tenant_name ?? '—',
          },
        ]
      : []),
    {
      key: 'status',
      header: 'Status',
      width: 'minmax(0,140px)',
      render: (task) => <Pill {...processInstanceStatusToPillProps(task.status)} />,
    },
    {
      key: 'created',
      header: (
        <button
          type="button"
          className="inline-flex items-center gap-1 tracking-[0.06em] uppercase text-foreground"
          onClick={toggleSort}
          aria-label={`Sort by created, ${sort === 'newest' ? 'newest first' : 'oldest first'}`}
          data-testid="task-review-sort-created"
        >
          Created
          <SortIcon className="size-3" aria-hidden />
        </button>
      ),
      width: 'minmax(0,120px)',
      className: 'text-muted-foreground',
      render: (task) =>
        task.created_at_in_seconds != null ? formatRelativeTime(task.created_at_in_seconds) : '—',
    },
  ];

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">Task Review</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Pending tasks awaiting your review.
        </p>
      </div>

      <Card variant="bordered" className="overflow-hidden">
        <div aria-busy={loading}>
          {error ? (
            <p className="px-6 py-4 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}

          {loading ? (
            <p className="px-6 py-6 text-sm text-muted-foreground">Loading…</p>
          ) : null}

          {!loading && !error && tasks.length === 0 ? (
            <p className="px-6 py-6 text-sm text-muted-foreground">No pending tasks.</p>
          ) : null}

          {!loading && !error && tasks.length > 0 ? (
            <DataTable
              columns={columns}
              rows={tasks}
              getRowKey={(task) => task.id}
              onRowClick={(task) => navigate(`/task-review/${task.id}`)}
              className="text-sm"
              minWidth="640px"
            />
          ) : null}
        </div>
      </Card>

      {!loading && !error && total > 0 ? (
        <div className="mt-4">
          <Pagination page={page} onPageChange={setPage} totalItems={total} pageSize={PER_PAGE} />
        </div>
      ) : null}
    </main>
  );
}

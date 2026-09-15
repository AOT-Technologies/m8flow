import { useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';

import { fetchHomeRecentInstances, type HomeRecentInstance } from '@/lib/api';
import { formatRelativeTime } from '@/lib/relativeTime';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { processInstanceStatusToPillProps } from '@/components/library/pill/processInstanceStatusToPillProps';
import { Card } from '@/components/ui/card';

export type RecentInstancesTableProps = {
  tenantId?: string | null;
  /** When set, skip the network fetch (prototype / tests). */
  rows?: HomeRecentInstance[] | null;
};

/**
 * Home "Recent process instances" table — Tenant / ID / Process / Started /
 * Status + a link to that instance's detail page. "View all" links to the
 * unfiltered Process Instances list (Process Instances + task-state map,
 * ticket 04 capstone — both were inert until that map's own
 * `/process-instances`(+`/:id`) routes existed).
 */
export function RecentInstancesTable({
  tenantId = null,
  rows: rowsOverride,
}: RecentInstancesTableProps) {
  const [rows, setRows] = useState<HomeRecentInstance[]>(rowsOverride ?? []);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(rowsOverride === undefined);

  useEffect(() => {
    if (rowsOverride !== undefined) {
      setRows(rowsOverride ?? []);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchHomeRecentInstances(tenantId)
      .then((payload) => {
        if (!cancelled) {
          setRows(payload);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load instances');
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
  }, [tenantId, rowsOverride]);

  const columns: DataTableColumn<HomeRecentInstance>[] = [
    {
      key: 'tenant',
      header: 'Tenant',
      width: '110px',
      render: (row) => <div className="truncate text-[13.5px] text-foreground">{row.tenant_name}</div>,
    },
    {
      key: 'id',
      header: 'ID',
      width: '64px',
      render: (row) => <span className="font-mono text-[13px] text-muted-foreground">{row.id}</span>,
    },
    {
      key: 'process',
      header: 'Process',
      render: (row) => (
        <div className="truncate text-[13.5px] text-foreground">{row.process_model_display_name}</div>
      ),
    },
    {
      key: 'started',
      header: 'Started',
      width: '110px',
      render: (row) => (
        <span className="text-[13px] text-muted-foreground">
          {formatRelativeTime(row.start_in_seconds)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '150px',
      render: (row) => <Pill {...processInstanceStatusToPillProps(row.status)} />,
    },
    {
      key: 'actions',
      header: null,
      width: '40px',
      className: 'flex justify-end',
      render: (row) => (
        <Link
          to={`/process-instances/${row.id}`}
          title="Open instance"
          aria-label={`Open instance ${row.id}`}
          className="flex size-7 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <ExternalLink className="size-[15px]" aria-hidden />
        </Link>
      ),
    },
  ];

  return (
    <Card variant="bordered" className="overflow-hidden">
      <div className="flex items-center justify-between px-[22px] py-[18px]">
        <h2 className="text-[15px] font-semibold text-foreground">Recent process instances</h2>
        <Link
          to="/process-instances"
          className="text-[13px] font-semibold text-info no-underline hover:underline"
        >
          View all
        </Link>
      </div>

      {error ? (
        <p className="border-t border-border px-[22px] py-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <div
          className="border-t border-border px-[22px] py-4 text-sm text-muted-foreground"
          aria-busy="true"
        >
          Loading…
        </div>
      ) : rows.length === 0 && !error ? (
        <div className="border-t border-border px-[22px] py-4 text-sm text-muted-foreground">
          No recent process instances.
        </div>
      ) : (
        <DataTable columns={columns} rows={rows} getRowKey={(row) => row.id} />
      )}
    </Card>
  );
}

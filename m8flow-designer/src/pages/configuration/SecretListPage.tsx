import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  deleteSecret,
  fetchSecrets,
  secretsErrorMessage,
  type Secret,
  type SecretPagination,
} from '@/lib/secretsApi';

import { ConfigurationGate, useConfigurationContext } from './ConfigurationGate';

const PER_PAGE = 10;
const TITLE = 'Configuration';

export default function SecretListPage() {
  return (
    <ConfigurationGate title={TITLE}>
      <SecretListBody />
    </ConfigurationGate>
  );
}

function SecretListBody() {
  const { scopedTenantId, isSuperAdmin, canManageSecrets } = useConfigurationContext();
  const [rows, setRows] = useState<Secret[]>([]);
  const [pagination, setPagination] = useState<SecretPagination | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [pendingDelete, setPendingDelete] = useState<Secret | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSecrets({ page, perPage: PER_PAGE, tenantId: scopedTenantId })
      .then((payload) => {
        if (!cancelled) {
          setRows(payload.results);
          setPagination(payload.pagination);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(secretsErrorMessage(err, 'Could not list secrets.'));
          setRows([]);
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
  }, [page, scopedTenantId, reloadKey]);

  async function performDelete() {
    const target = pendingDelete;
    setPendingDelete(null);
    if (!target) return;
    setError(null);
    try {
      await deleteSecret(target.key, scopedTenantId);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setError(secretsErrorMessage(err, 'Could not delete secret.'));
    }
  }

  const columns: DataTableColumn<Secret>[] = [
    {
      key: 'key',
      header: 'Key',
      width: 'minmax(160px,1.6fr)',
      render: (row) => (
        <Link
          className="font-medium text-foreground underline-offset-4 hover:underline"
          to={`/configuration/secrets/${encodeURIComponent(row.key)}`}
        >
          {row.key}
        </Link>
      ),
    },
    {
      key: 'createdBy',
      header: 'Created by',
      width: 'minmax(120px,1fr)',
      render: (row) => <span className="text-muted-foreground">{row.username || '—'}</span>,
    },
    ...(isSuperAdmin
      ? [
          {
            key: 'tenant',
            header: 'Tenant',
            width: 'minmax(120px,1fr)',
            render: (row) => (
              <span className="text-muted-foreground" data-testid="secret-list-tenant-cell">
                {row.tenantName || row.tenantId || '—'}
              </span>
            ),
          } satisfies DataTableColumn<Secret>,
        ]
      : []),
    ...(canManageSecrets
      ? [
          {
            key: 'actions',
            header: <span className="sr-only">Actions</span>,
            className: 'text-right',
            width: 'minmax(80px,100px)',
            render: (row) => (
              <Button type="button" variant="ghost" size="sm" onClick={() => setPendingDelete(row)}>
                Delete
              </Button>
            ),
          } satisfies DataTableColumn<Secret>,
        ]
      : []),
  ];

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{TITLE}</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Tenant-scoped named credentials. After create, the value is never shown again.
          </p>
        </div>
        {canManageSecrets ? (
          <Button asChild variant="pill-dark" size="pill">
            <Link to="/configuration/secrets/new">
              <Plus className="size-3.5" aria-hidden />
              Add a secret
            </Link>
          </Button>
        ) : null}
      </div>

      {error ? (
        <Alert tone="error" className="mb-4" data-testid="secret-list-error">
          {error}
        </Alert>
      ) : null}

      <Card variant="bordered" className="overflow-hidden">
        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">Loading secrets…</p>
        ) : rows.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">
            No secrets in this tenant yet.
          </p>
        ) : (
          <DataTable columns={columns} rows={rows} getRowKey={(row) => row.key} />
        )}
        {pagination && pagination.pages > 1 ? (
          <div className="border-t border-border px-[22px] py-3">
            <Pagination
              page={page}
              onPageChange={setPage}
              totalItems={pagination.total}
              pageSize={PER_PAGE}
            />
          </div>
        ) : null}
      </Card>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete secret?"
        description={`Delete secret "${pendingDelete?.key ?? ''}"? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={() => void performDelete()}
      />
    </main>
  );
}

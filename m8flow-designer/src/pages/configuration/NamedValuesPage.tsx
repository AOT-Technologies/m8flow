import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  deleteNamedValue,
  fetchNamedValues,
  namedValuesErrorMessage,
  type NamedValue,
} from '@/lib/namedValuesApi';
import { formatRelativeTimeVerbose } from '@/lib/relativeTime';
import { ApiError } from '@/lib/api';

import { NamedValuesAccessDenied, NamedValuesGate, useNamedValuesContext } from './NamedValuesGate';

export default function NamedValuesPage() {
  const { t } = useTranslation();
  const { tenantId, isSuperAdmin } = useNamedValuesContext();
  return (
    <NamedValuesGate title={t('configuration.namedValues.title')}>
      {/* Discard tenant-owned rows and dialogs in render, before fetch effects run. */}
      <NamedValuesBody key={JSON.stringify([tenantId, isSuperAdmin])} />
    </NamedValuesGate>
  );
}

function NamedValuesBody() {
  const { t } = useTranslation();
  const {
    tenantId,
    isSuperAdmin,
    canCreateNamedValues,
    canReadNamedValueItems,
    canUpdateNamedValues,
    canDeleteNamedValues,
  } = useNamedValuesContext();
  const canEditNamedValues = canReadNamedValueItems && canUpdateNamedValues;
  const [rows, setRows] = useState<NamedValue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<NamedValue | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setAccessDenied(false);
    setActionError(null);
    setPendingDelete(null);
    fetchNamedValues(isSuperAdmin ? tenantId : null)
      .then((result) => {
        if (!cancelled) setRows(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setRows([]);
          setAccessDenied(err instanceof ApiError && err.status === 403);
          setError(namedValuesErrorMessage(err, t('configuration.namedValues.errors.list')));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isSuperAdmin, tenantId, reloadKey, t]);

  async function confirmDelete() {
    const target = pendingDelete;
    setPendingDelete(null);
    if (!target || !canDeleteNamedValues) return;
    setActionError(null);
    try {
      await deleteNamedValue(target.id, isSuperAdmin ? tenantId : null);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setActionError(namedValuesErrorMessage(err, t('configuration.namedValues.errors.delete')));
    }
  }

  const columns: DataTableColumn<NamedValue>[] = [
    {
      key: 'name',
      header: t('configuration.namedValues.columns.name'),
      width: 'minmax(160px,1.5fr)',
      render: (row) => (
        <div>
          <span className="font-medium text-foreground">{row.name}</span>
          {row.description ? <p className="mt-1 text-[13px] text-muted-foreground">{row.description}</p> : null}
        </div>
      ),
    },
    {
      key: 'sensitivity',
      header: t('configuration.namedValues.columns.sensitivity'),
      width: 'minmax(130px,1fr)',
      render: (row) => t(row.isSensitive ? 'configuration.namedValues.sensitive' : 'configuration.namedValues.standard'),
    },
    {
      key: 'configured',
      header: t('configuration.namedValues.columns.value'),
      width: 'minmax(110px,1fr)',
      render: (row) => t(row.isConfigured ? 'configuration.namedValues.configured' : 'configuration.namedValues.notConfigured'),
    },
    {
      key: 'updated',
      header: t('configuration.namedValues.columns.updated'),
      width: 'minmax(130px,1fr)',
      render: (row) => <span className="text-[13px] text-muted-foreground">{formatRelativeTimeVerbose(row.updatedAt)}</span>,
    },
    ...(canReadNamedValueItems || canDeleteNamedValues
      ? [
          {
            key: 'actions',
            header: <span className="sr-only">{t('common.actions')}</span>,
            className: 'text-right',
            width: 'minmax(130px,1fr)',
            render: (row) => (
              <div className="flex justify-end gap-1">
                {canReadNamedValueItems ? (
                  <Button asChild variant="ghost" size="sm">
                    <Link to={`/configuration/named-values/${encodeURIComponent(row.id)}`}>
                      {t(canEditNamedValues ? 'configuration.namedValues.edit.action' : 'configuration.namedValues.view.action')}
                    </Link>
                  </Button>
                ) : null}
                {canDeleteNamedValues ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setPendingDelete(row)}>
                    {t('common.delete')}
                  </Button>
                ) : null}
              </div>
            ),
          } satisfies DataTableColumn<NamedValue>,
        ]
      : []),
  ];

  if (accessDenied) {
    return <NamedValuesAccessDenied title={t('configuration.namedValues.title')} />;
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[32px] font-semibold tracking-tight">
            {t('configuration.namedValues.title')}
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            {t('configuration.namedValues.subtitle')}
          </p>
        </div>
        {canCreateNamedValues ? (
          <Button asChild variant="pill-dark" size="pill">
            <Link to="/configuration/named-values/new">
              <Plus className="size-3.5" aria-hidden />
              {t('configuration.namedValues.add')}
            </Link>
          </Button>
        ) : null}
      </div>

      {error ? <Alert tone="error" className="mb-4">{error}</Alert> : null}
      {actionError ? <Alert tone="error" className="mb-4">{actionError}</Alert> : null}
      {!error && <Card variant="bordered" className="overflow-hidden">
        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">{t('configuration.namedValues.loading')}</p>
        ) : rows.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">{t('configuration.namedValues.empty')}</p>
        ) : (
          <DataTable columns={columns} rows={rows} getRowKey={(row) => row.id} />
        )}
      </Card>}
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title={t('configuration.namedValues.deleteTitle')}
        description={t('configuration.namedValues.deleteDescription', { name: pendingDelete?.name ?? '' })}
        confirmLabel={t('common.delete')}
        onConfirm={() => void confirmDelete()}
      />
    </main>
  );
}

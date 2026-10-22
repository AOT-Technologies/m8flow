import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { fetchCeleryTaskTypes, setCeleryRateLimit, setCeleryTimeLimit, type CeleryTaskType } from '@/lib/celeryApi';
import { formatNumber } from '@/pages/nats/natsShared';

import { WINDOW_OPTIONS } from './CeleryTasksTab';
import { CeleryActionDialog, celeryErrorMessage, formatRuntime, formatTimestamp, type Notice, useActionDialog } from './celeryShared';

function seconds(value: string): number | null {
  return value.trim() === '' ? null : Number(value);
}

/** Per task type: outcomes and runtimes from history, with Flower's rate and time limits. */
export function CeleryTaskTypesTab({
  historyEnabled,
  canControl,
  refreshKey,
  onShowHistory,
  onNotice,
}: {
  historyEnabled: boolean;
  canControl: boolean;
  refreshKey: number;
  onShowHistory: (taskName: string) => void;
  onNotice: (notice: Notice) => void;
}) {
  const { t } = useTranslation();
  const [windowValue, setWindowValue] = useState('24');
  const [rows, setRows] = useState<CeleryTaskType[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialog = useActionDialog<{ kind: 'rate' | 'time'; name: string }>();

  useEffect(() => {
    let cancelled = false;
    fetchCeleryTaskTypes(windowValue === '__all__' ? null : Number(windowValue))
      .then((next) => {
        if (!cancelled) {
          setRows(next);
          setError(null);
        }
      })
      .catch((err) => !cancelled && setError(celeryErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [windowValue, refreshKey]);

  const count = (value: number, tone?: string) => (
    <span className={`font-mono ${value && tone ? tone : ''}`}>{formatNumber(value)}</span>
  );

  const columns: DataTableColumn<CeleryTaskType>[] = [
    {
      key: 'name',
      header: t('celery.taskTypes.name'),
      width: 'minmax(260px,3fr)',
      render: (row) => (
        <button
          type="button"
          className="text-left font-mono text-[12.5px] break-all text-foreground underline-offset-2 hover:underline"
          onClick={() => onShowHistory(row.name)}
        >
          {row.name}
        </button>
      ),
    },
    { key: 'total', header: t('celery.taskTypes.total'), render: (row) => count(row.total) },
    { key: 'succeeded', header: t('celery.taskTypes.succeeded'), render: (row) => count(row.succeeded, 'text-success') },
    { key: 'failed', header: t('celery.taskTypes.failed'), render: (row) => count(row.failed, 'text-destructive') },
    { key: 'retried', header: t('celery.taskTypes.retried'), render: (row) => count(row.retried, 'text-warning') },
    { key: 'running', header: t('celery.taskTypes.running'), render: (row) => count(row.running) },
    { key: 'avg', header: t('celery.taskTypes.avgRuntime'), render: (row) => <span className="font-mono">{formatRuntime(row.avgRuntimeSeconds)}</span> },
    { key: 'max', header: t('celery.taskTypes.maxRuntime'), render: (row) => <span className="font-mono">{formatRuntime(row.maxRuntimeSeconds)}</span> },
    { key: 'lastSeen', header: t('celery.taskTypes.lastSeen'), render: (row) => formatTimestamp(row.lastSeenAt) },
    ...(canControl
      ? [
          {
            key: 'actions',
            header: '',
            width: 'minmax(200px,1fr)',
            className: 'text-right',
            render: (row: CeleryTaskType) => (
              <>
                <Button variant="link" size="sm" onClick={() => dialog.open({ kind: 'rate', name: row.name })}>
                  {t('celery.actions.rateLimit')}
                </Button>
                <Button variant="link" size="sm" onClick={() => dialog.open({ kind: 'time', name: row.name })}>
                  {t('celery.actions.timeLimit')}
                </Button>
              </>
            ),
          },
        ]
      : []),
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">
          {historyEnabled ? t('celery.taskTypes.subtitle') : t('celery.taskTypes.noHistory')}
        </p>
        <Select value={windowValue} onValueChange={setWindowValue}>
          <SelectTrigger aria-label={t('celery.history.window')} className="h-9 w-48 rounded-lg text-[13px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WINDOW_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {t(option.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <Card variant="bordered">
        <DataTable
          columns={columns}
          rows={rows ?? []}
          minWidth="1100px"
          getRowKey={(row) => row.name}
          emptyState={rows ? t('celery.taskTypes.empty') : t('common.loading')}
        />
      </Card>
      {dialog.target && (
        <CeleryActionDialog
          {...dialog.props}
          title={t(dialog.target.kind === 'rate' ? 'celery.dialogs.rateLimitTitle' : 'celery.dialogs.timeLimitTitle')}
          description={t(dialog.target.kind === 'rate' ? 'celery.dialogs.rateLimitBody' : 'celery.dialogs.timeLimitBody', {
            name: dialog.target.name,
          })}
          confirmLabel={t('celery.actions.apply')}
          fields={
            dialog.target.kind === 'rate'
              ? [{ key: 'rate', label: t('celery.dialogs.fieldRate'), placeholder: '10/m' }]
              : [
                  { key: 'soft', label: t('celery.dialogs.fieldSoft'), type: 'number', placeholder: '30' },
                  { key: 'hard', label: t('celery.dialogs.fieldHard'), type: 'number', placeholder: '60' },
                ]
          }
          onSubmit={(values) =>
            dialog.target!.kind === 'rate'
              ? setCeleryRateLimit(dialog.target!.name, values.rate.trim())
              : setCeleryTimeLimit(dialog.target!.name, seconds(values.soft), seconds(values.hard))
          }
          onDone={onNotice}
        />
      )}
    </div>
  );
}

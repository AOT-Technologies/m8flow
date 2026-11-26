import { useEffect, useState } from 'react';
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/lib/api';
import {
  fetchExternalFormEmails,
  resendExternalFormEmail,
  type ExternalFormEmail,
  type ExternalFormEmailStatus,
} from '@/lib/externalFormNotificationsApi';
import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { EmptyState } from '@/components/library/empty-state/EmptyState';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

type Tone = 'success' | 'error' | 'warning' | 'muted' | 'info';

type StatusStyle = { labelKey: ParseKeys; tone: Tone };

const STATUS: Record<ExternalFormEmailStatus, StatusStyle> = {
  pending: { labelKey: 'processInstances.emails.status.pending', tone: 'info' },
  sending: { labelKey: 'processInstances.emails.status.sending', tone: 'info' },
  notified: { labelKey: 'processInstances.emails.status.notified', tone: 'success' },
  failed: { labelKey: 'processInstances.emails.status.failed', tone: 'error' },
  smtp_unconfigured: { labelKey: 'processInstances.emails.status.smtpUnconfigured', tone: 'error' },
  expired: { labelKey: 'processInstances.emails.status.expired', tone: 'warning' },
  cancelled: { labelKey: 'processInstances.emails.status.cancelled', tone: 'muted' },
  submitted: { labelKey: 'processInstances.emails.status.submitted', tone: 'success' },
  completed: { labelKey: 'processInstances.emails.status.submitted', tone: 'success' },
  superseded: { labelKey: 'processInstances.emails.status.superseded', tone: 'muted' },
};

function formatSeconds(seconds: number | null): string {
  if (seconds == null) return '—';
  const d = new Date(seconds * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

export type ProcessInstanceExternalFormEmailsTableProps = {
  instanceId: number;
  /** The instance's own tenant: the list and resend need one concrete tenant. */
  tenantId?: string | null;
  /** From the backend permission check (POST /secrets); hides Resend when false. */
  canResend: boolean;
};

/**
 * External Form Emails tab: one row per recipient of each external-form task in this
 * instance, with delivery status and a Resend action. Backed by
 * GET/POST /v1.0/m8flow/external-form-notifications (secrets permission).
 */
export function ProcessInstanceExternalFormEmailsTable({
  instanceId,
  tenantId = null,
  canResend,
}: ProcessInstanceExternalFormEmailsTableProps) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<ExternalFormEmail[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingResend, setPendingResend] = useState<ExternalFormEmail | null>(null);
  const [resending, setResending] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchExternalFormEmails(instanceId, tenantId)
      .then((payload) => {
        if (!cancelled) {
          setRows(payload.results);
          setTotal(payload.pagination.total);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setRows([]);
          setError(t('processInstances.emails.loadError'));
          if (err instanceof ApiError && err.serverMessage) setError(err.serverMessage);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [instanceId, tenantId, reloadKey, t]);

  async function confirmResend() {
    const target = pendingResend;
    if (!target) return;
    setResending(true);
    setError(null);
    setNotice(null);
    try {
      await resendExternalFormEmail(target.id, tenantId);
      setNotice(t('processInstances.emails.resendSuccess', { email: target.email }));
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setError(
        err instanceof ApiError && err.serverMessage ? err.serverMessage : t('processInstances.emails.resendError'),
      );
    } finally {
      setResending(false);
      setPendingResend(null);
    }
  }

  const columns: DataTableColumn<ExternalFormEmail>[] = [
    {
      key: 'email',
      header: t('processInstances.emails.columns.recipient'),
      width: 'minmax(180px,1.6fr)',
      className: 'min-w-0 text-[14px] text-foreground',
      render: (row) => (
        <span className="block truncate" title={row.email}>
          {row.email}
        </span>
      ),
    },
    {
      key: 'task',
      header: t('processInstances.emails.columns.task'),
      width: 'minmax(140px,1.2fr)',
      render: (row) => row.task_title || row.task_name || '—',
    },
    {
      key: 'status',
      header: t('processInstances.emails.columns.status'),
      width: 'minmax(150px,1.2fr)',
      render: (row) => {
        // A status this UI doesn't know yet shows as-is rather than as a misleading label.
        const status = (STATUS as Partial<Record<string, StatusStyle>>)[row.effective_status];
        return (
          <div className="flex flex-col items-start gap-1">
            <Pill tone={status?.tone ?? 'muted'}>{status ? t(status.labelKey) : row.effective_status}</Pill>
            {row.stuck_sending ? (
              <span className="text-[12px] text-warning">{t('processInstances.emails.stuckSending')}</span>
            ) : null}
          </div>
        );
      },
    },
    {
      key: 'sent',
      header: t('processInstances.emails.columns.sent'),
      width: '140px',
      className: 'whitespace-nowrap font-mono text-[12.5px]',
      // While "sending", notified_at is the worker's claim time, not a delivery.
      render: (row) => formatSeconds(row.status === 'sending' ? null : row.notified_at_in_seconds),
    },
    {
      key: 'expires',
      header: t('processInstances.emails.columns.expires'),
      width: '140px',
      className: 'whitespace-nowrap font-mono text-[12.5px]',
      render: (row) => formatSeconds(row.expires_at_in_seconds),
    },
    {
      key: 'error',
      header: t('processInstances.emails.columns.error'),
      width: 'minmax(160px,1.6fr)',
      className: 'min-w-0 break-words text-[13px] text-muted-foreground',
      // A cancelled row's reason is the backend's English sentence; its status and the
      // notice above already say it in the user's language.
      render: (row) => (row.effective_status === 'cancelled' ? '—' : row.last_error || '—'),
    },
    ...(canResend
      ? [
          {
            key: 'actions',
            header: <span className="sr-only">{t('common.actions')}</span>,
            className: 'text-right',
            width: 'minmax(90px,110px)',
            render: (row) =>
              row.resendable ? (
                <Button type="button" variant="ghost" size="sm" onClick={() => setPendingResend(row)}>
                  {t('processInstances.emails.resend')}
                </Button>
              ) : null,
          } satisfies DataTableColumn<ExternalFormEmail>,
        ]
      : []),
  ];

  const anyCancelled = rows.some((row) => row.effective_status === 'cancelled');

  return (
    <>
      {notice ? (
        <Alert tone="success" className="mb-4" role="status">
          {notice}
        </Alert>
      ) : null}
      {error ? (
        <Alert tone="error" className="mb-4">
          {error}
        </Alert>
      ) : null}
      {total > rows.length ? (
        <Alert tone="info" className="mb-4">
          {t('processInstances.emails.truncated', { shown: rows.length, total })}
        </Alert>
      ) : null}
      {anyCancelled ? (
        <Alert tone="info" className="mb-4">
          {t('processInstances.emails.cancelledNotice')}
        </Alert>
      ) : null}

      {loading ? (
        <p className="py-8 text-sm text-muted-foreground" aria-busy="true">
          {t('processInstances.emails.loading')}
        </p>
      ) : rows.length === 0 && !error ? (
        <EmptyState title={t('processInstances.emails.empty')} />
      ) : rows.length > 0 ? (
        <Card variant="bordered" className="overflow-x-auto">
          <DataTable columns={columns} rows={rows} getRowKey={(row) => String(row.id)} emptyState="" minWidth="1100px" />
        </Card>
      ) : null}

      <ConfirmDialog
        open={pendingResend !== null}
        onOpenChange={(open) => {
          if (!open && !resending) setPendingResend(null);
        }}
        title={t('processInstances.emails.resendConfirm.title')}
        description={t('processInstances.emails.resendConfirm.description', { email: pendingResend?.email ?? '' })}
        confirmLabel={t('processInstances.emails.resend')}
        tone="default"
        pending={resending}
        onConfirm={() => void confirmResend()}
      />
    </>
  );
}

import { useEffect, useState, type FormEvent } from 'react';
import { Check, ChevronDown, Copy, Plus } from 'lucide-react';
import type { ParseKeys } from 'i18next';
import { Trans, useTranslation } from 'react-i18next';

import { formatLocale } from '@/i18n';
import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pill } from '@/components/library/pill/Pill';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  createNatsApiKey,
  fetchNatsApiKeys,
  natsTokensErrorMessage,
  revokeNatsApiKey,
  type CreatedNatsApiKey,
  type NatsApiKey,
  type NatsApiKeyExpiryDays,
} from '@/lib/natsTokensApi';
import { formatRelativeTime } from '@/lib/relativeTime';

const MAX_LABEL_LENGTH = 255;
const EXPIRY_OPTIONS: { value: string; days: NatsApiKeyExpiryDays; labelKey: ParseKeys }[] = [
  { value: '30', days: 30, labelKey: 'apiKeys.expiry.days30' },
  { value: '90', days: 90, labelKey: 'apiKeys.expiry.days90' },
  { value: '365', days: 365, labelKey: 'apiKeys.expiry.oneYear' },
  { value: 'never', days: null, labelKey: 'apiKeys.never' },
];
const DEFAULT_EXPIRY = '90';

function formatDate(epochSeconds: number | null | undefined): string {
  return epochSeconds ? new Date(epochSeconds * 1000).toLocaleDateString(formatLocale()) : '—';
}

/** Revoked wins over expired; the backend reports neither as a status field. */
function keyStatus(key: NatsApiKey, nowSeconds: number): 'Active' | 'Expired' | 'Revoked' {
  if (key.revokedAtInSeconds) return 'Revoked';
  if (key.expiresAtInSeconds && key.expiresAtInSeconds < nowSeconds) return 'Expired';
  return 'Active';
}

const STATUS_TONE = { Active: 'success', Expired: 'warning', Revoked: 'muted' } as const;
const STATUS_LABEL = {
  Active: 'apiKeys.status.active',
  Expired: 'apiKeys.status.expired',
  Revoked: 'apiKeys.status.revoked',
} as const;

export default function ApiKeysPage() {
  const { t } = useTranslation();
  const { needsTenant } = useActiveTenant();
  if (needsTenant) {
    return (
      <main className="flex-1 px-11 py-10">
        <h1 className="mb-7 font-display text-[32px] font-semibold tracking-tight">{t('apiKeys.title')}</h1>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">{t('apiKeys.chooseTenantTitle')}</p>
          <p className="mt-2 text-sm text-muted-foreground">{t('apiKeys.chooseTenantBody')}</p>
        </Card>
      </main>
    );
  }
  return <ApiKeysBody />;
}

function ApiKeysBody() {
  const { t } = useTranslation();
  const { scopedTenantId } = useActiveTenant();
  const { canManageNatsApiKeys, canRevokeNatsApiKeys } = useCapabilities();
  const [rows, setRows] = useState<NatsApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  // The raw key lives only here, in memory, until Done or navigation.
  const [created, setCreated] = useState<CreatedNatsApiKey | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<NatsApiKey | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchNatsApiKeys(scopedTenantId)
      .then((keys) => {
        if (!cancelled) setRows(keys);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(natsTokensErrorMessage(err, t('apiKeys.errors.load')));
          setRows([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scopedTenantId, reloadKey]);

  async function performRevoke() {
    const target = pendingRevoke;
    setPendingRevoke(null);
    if (!target) return;
    setError(null);
    try {
      await revokeNatsApiKey(target.id, scopedTenantId);
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setError(natsTokensErrorMessage(err, t('apiKeys.errors.revoke')));
    }
  }

  const nowSeconds = Math.floor(Date.now() / 1000);
  const columns: DataTableColumn<NatsApiKey>[] = [
    {
      key: 'label',
      header: t('common.name'),
      width: 'minmax(160px,1.4fr)',
      render: (row) => <span className="font-medium text-foreground">{row.label}</span>,
    },
    {
      key: 'scope',
      header: t('apiKeys.columns.allowedProcesses'),
      width: 'minmax(160px,1.4fr)',
      render: (row) => (
        <span className="break-words text-muted-foreground">
          {row.scope ? row.scope.split(',').join(', ') : t('apiKeys.anyProcess')}
        </span>
      ),
    },
    {
      key: 'created',
      header: t('apiKeys.columns.created'),
      width: 'minmax(110px,1fr)',
      render: (row) => (
        <span className="text-muted-foreground">
          {formatDate(row.createdAtInSeconds)}
          {row.createdBy ? (
            <span className="block text-xs">{t('apiKeys.createdBy', { user: row.createdBy })}</span>
          ) : null}
        </span>
      ),
    },
    {
      key: 'expires',
      header: t('apiKeys.columns.expires'),
      width: 'minmax(100px,0.8fr)',
      render: (row) => (
        <span className="text-muted-foreground">
          {row.expiresAtInSeconds ? formatDate(row.expiresAtInSeconds) : t('apiKeys.never')}
        </span>
      ),
    },
    {
      key: 'lastUsed',
      header: t('apiKeys.columns.lastUsed'),
      width: 'minmax(90px,0.8fr)',
      render: (row) => (
        <span className="text-muted-foreground">
          {row.lastUsedAtInSeconds ? formatRelativeTime(row.lastUsedAtInSeconds) : t('apiKeys.never')}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      width: 'minmax(90px,0.7fr)',
      render: (row) => {
        const status = keyStatus(row, nowSeconds);
        return <Pill tone={STATUS_TONE[status]}>{t(STATUS_LABEL[status])}</Pill>;
      },
    },
    ...(canRevokeNatsApiKeys
      ? [
          {
            key: 'actions',
            header: <span className="sr-only">{t('common.actions')}</span>,
            className: 'text-right',
            width: 'minmax(80px,100px)',
            render: (row) =>
              row.revokedAtInSeconds ? null : (
                <Button type="button" variant="ghost" size="sm" onClick={() => setPendingRevoke(row)}>
                  {t('apiKeys.revoke')}
                </Button>
              ),
          } satisfies DataTableColumn<NatsApiKey>,
        ]
      : []),
  ];

  return (
    <main className="flex-1 px-11 py-10" data-testid="api-keys-page">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{t('apiKeys.title')}</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">{t('apiKeys.subtitle')}</p>
        </div>
        {canManageNatsApiKeys ? (
          <Button type="button" variant="pill-dark" size="pill" onClick={() => setCreateOpen(true)}>
            <Plus className="size-3.5" aria-hidden />
            {t('apiKeys.createKey')}
          </Button>
        ) : null}
      </div>

      {error ? (
        <Alert tone="error" className="mb-4" data-testid="api-keys-error">
          {error}
        </Alert>
      ) : null}

      {created ? <CreatedKeyPanel created={created} onDone={() => setCreated(null)} /> : null}

      <Card variant="bordered" className="overflow-hidden">
        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">{t('apiKeys.loading')}</p>
        ) : rows.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">{t('apiKeys.empty')}</p>
        ) : (
          <DataTable columns={columns} rows={rows} getRowKey={(row) => row.id} minWidth="900px" />
        )}
      </Card>

      <Modal open={createOpen} onOpenChange={setCreateOpen} title={t('apiKeys.createKey')}>
        <CreateKeyForm
          tenantId={scopedTenantId}
          onCancel={() => setCreateOpen(false)}
          onCreated={(key) => {
            setCreateOpen(false);
            setCreated(key);
            setReloadKey((value) => value + 1);
          }}
        />
      </Modal>

      <ConfirmDialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
        title={t('apiKeys.revokeDialog.title')}
        description={t('apiKeys.revokeDialog.description', { label: pendingRevoke?.label ?? '' })}
        confirmLabel={t('apiKeys.revoke')}
        onConfirm={() => void performRevoke()}
      />
    </main>
  );
}

/** Rendered inside the Modal, so its state resets every time the modal opens. */
function CreateKeyForm({
  tenantId,
  onCancel,
  onCreated,
}: {
  tenantId: string | null;
  onCancel: () => void;
  onCreated: (key: CreatedNatsApiKey) => void;
}) {
  const { t } = useTranslation();
  const [label, setLabel] = useState('');
  const [scope, setScope] = useState('');
  const [expiry, setExpiry] = useState(DEFAULT_EXPIRY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmedLabel = label.trim();
    if (!trimmedLabel || submitting) return;
    const scopes = scope
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean);
    const expiresInDays = EXPIRY_OPTIONS.find((option) => option.value === expiry)?.days ?? null;
    setSubmitting(true);
    setError(null);
    try {
      onCreated(
        await createNatsApiKey(
          { label: trimmedLabel, expiresInDays, ...(scopes.length ? { scope: scopes } : {}) },
          tenantId,
        ),
      );
    } catch (err: unknown) {
      setError(natsTokensErrorMessage(err, t('apiKeys.errors.create')));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      <label className="block text-sm font-medium text-foreground">
        {t('common.name')}
        <Input
          className="mt-1.5"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          maxLength={MAX_LABEL_LENGTH}
          autoComplete="off"
          placeholder={t('apiKeys.form.labelPlaceholder')}
          data-testid="api-key-label"
          required
        />
      </label>
      <label className="mt-4 block text-sm font-medium text-foreground">
        {t('apiKeys.form.allowedProcesses')}{' '}
        <span className="font-normal text-muted-foreground">{t('apiKeys.form.optional')}</span>
        <Input
          className="mt-1.5"
          value={scope}
          onChange={(event) => setScope(event.target.value)}
          autoComplete="off"
          placeholder={t('apiKeys.form.scopePlaceholder')}
          data-testid="api-key-scope"
        />
        <span className="mt-1 block text-xs font-normal text-muted-foreground">
          {t('apiKeys.form.scopeHint')}
        </span>
      </label>
      <label className="mt-4 block text-sm font-medium text-foreground">
        {t('apiKeys.form.expiresAfter')}
        <span className="relative mt-1.5 block">
          <select
            className="h-8 w-full appearance-none rounded-lg border border-input bg-transparent pr-8 pl-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            value={expiry}
            onChange={(event) => setExpiry(event.target.value)}
            data-testid="api-key-expiry"
          >
            {EXPIRY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
        </span>
      </label>
      {error ? (
        <Alert tone="error" className="mt-3" data-testid="api-key-create-error">
          {error}
        </Alert>
      ) : null}
      <div className="mt-6 flex justify-end gap-2.5">
        <Button type="button" variant="pill-cancel" size="pill" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button
          type="submit"
          variant="pill-dark"
          size="pill"
          disabled={!label.trim() || submitting}
          data-testid="api-key-create"
        >
          {submitting ? t('apiKeys.form.creating') : t('apiKeys.form.create')}
        </Button>
      </div>
    </form>
  );
}

function CreatedKeyPanel({ created, onDone }: { created: CreatedNatsApiKey; onDone: () => void }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(created.token);
      setCopyError(null);
      setCopied(true);
    } catch {
      setCopied(false);
      setCopyError(t('apiKeys.errors.copy'));
    }
  }

  return (
    <Card variant="bordered" className="mb-4 p-6" data-testid="api-key-created">
      <Alert tone="warning">{t('apiKeys.created.warning')}</Alert>
      <p className="mt-4 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {created.label}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/30 p-3">
        <code
          className="min-w-0 flex-1 break-all text-sm text-foreground select-all"
          data-testid="api-key-token"
        >
          {created.token}
        </code>
        <Button type="button" variant="pill-outline" size="pill" onClick={() => void handleCopy()}>
          {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
          {copied ? t('apiKeys.created.copied') : t('apiKeys.created.copy')}
        </Button>
      </div>
      {copyError ? (
        <Alert tone="error" className="mt-3">
          {copyError}
        </Alert>
      ) : null}
      <p className="mt-3 text-sm text-muted-foreground">
        <Trans
          i18nKey="apiKeys.created.headerHint"
          values={{ header: 'X-M8FLOW-NATS-API-Key' }}
          components={{ code: <code /> }}
        />
      </p>
      <Button type="button" variant="pill-dark" size="pill" className="mt-4" onClick={onDone}>
        {t('apiKeys.created.done')}
      </Button>
    </Card>
  );
}

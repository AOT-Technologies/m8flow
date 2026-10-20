import { FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  deleteSecret,
  fetchSecret,
  secretsErrorMessage,
  updateSecret,
  type Secret,
} from '@/lib/secretsApi';

import { ConfigurationGate, useConfigurationContext } from './ConfigurationGate';
import { ConfigurationBackButton } from './ConfigurationBackButton';
import { SecretValueField } from './SecretValueField';

export default function SecretShowPage() {
  const { t } = useTranslation();
  return (
    <ConfigurationGate title={t('configuration.show.title')}>
      <SecretShowBody />
    </ConfigurationGate>
  );
}

function SecretShowBody() {
  const { t } = useTranslation();
  const { key: keyFromRoute } = useParams();
  const { scopedTenantId, canUpdateSecrets, canDeleteSecrets, needsTenantForWrite } = useConfigurationContext();
  const [searchParams] = useSearchParams();
  // Under All Tenants the list links carry the row's own tenant, so a secret
  // opened from the list resolves to exactly one tenant. Writes below stay
  // disabled when neither is available.
  const tenantId = searchParams.get('tenantId') || scopedTenantId;
  // Regular users are cookie-scoped and have no sidebar tenant; only an
  // All-Tenants super-admin without a ?tenantId is blocked from writing.
  const hasWriteTenant = !(needsTenantForWrite && !tenantId);
  const canUpdate = canUpdateSecrets && hasWriteTenant;
  const canDelete = canDeleteSecrets && hasWriteTenant;
  const navigate = useNavigate();
  const [entry, setEntry] = useState<Secret | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftOpen, setDraftOpen] = useState(false);
  const [draftValue, setDraftValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [updated, setUpdated] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (!keyFromRoute) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSecret(keyFromRoute, tenantId)
      .then((payload) => {
        if (!cancelled) {
          setEntry(payload);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(secretsErrorMessage(err, t('configuration.errors.load')));
          setEntry(null);
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
  }, [keyFromRoute, tenantId]);

  async function handleDelete() {
    if (!entry) {
      return;
    }
    setConfirmingDelete(false);
    setError(null);
    try {
      await deleteSecret(entry.key, tenantId);
      navigate('/configuration/secrets');
    } catch (err: unknown) {
      setError(secretsErrorMessage(err, t('configuration.errors.delete')));
    }
  }

  async function handleUpdate(event: FormEvent) {
    event.preventDefault();
    if (!entry || saving) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateSecret(entry.key, draftValue, tenantId);
      setDraftValue('');
      setDraftOpen(false);
      setUpdated(true);
    } catch (err: unknown) {
      setError(secretsErrorMessage(err, t('configuration.errors.update')));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <ConfigurationBackButton />
        <h1 className="font-display text-[32px] font-semibold tracking-tight">
          {entry?.key ?? t('configuration.show.title')}
        </h1>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          {t('configuration.show.subtitle')}
        </p>
      </div>

      {error ? (
        <Alert tone="error" className="mb-4">
          {error}
        </Alert>
      ) : null}

      {updated ? (
        <Alert tone="success" className="mb-4" data-testid="secret-updated">
          {t('configuration.show.updated')}
        </Alert>
      ) : null}

      <Card variant="bordered" className="max-w-lg p-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">{t('configuration.show.loading')}</p>
        ) : entry ? (
          <>
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
                  {t('configuration.secretKey')}
                </dt>
                <dd className="mt-1 font-medium" data-testid="secret-show-key">
                  {entry.key}
                </dd>
              </div>
            </dl>
            {canUpdate || canDelete ? (
              <div className="mt-6 flex flex-wrap gap-2">
                {canUpdate ? (
                <Button
                  type="button"
                  variant="pill-outline"
                  size="pill"
                  disabled={draftOpen}
                  onClick={() => {
                    setDraftOpen(true);
                    setDraftValue('');
                    setUpdated(false);
                  }}
                  data-testid="secret-edit"
                >
                  {t('configuration.show.editValue')}
                </Button>
                ) : null}
                {canDelete ? (
                  <Button type="button" variant="pill-outline" size="pill" className="text-destructive" onClick={() => setConfirmingDelete(true)}>
                    {t('common.delete')}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {canUpdate && draftOpen ? (
              <form className="mt-6" onSubmit={(event) => void handleUpdate(event)}>
                <SecretValueField
                  id="secret-value-input"
                  label={t('configuration.show.newValue')}
                  value={draftValue}
                  onChange={setDraftValue}
                />
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="pill-cancel"
                    size="pill"
                    onClick={() => {
                      setDraftOpen(false);
                      setDraftValue('');
                    }}
                  >
                    {t('common.cancel')}
                  </Button>
                  <Button
                    type="submit"
                    variant="pill-dark"
                    size="pill"
                    disabled={!draftValue || saving}
                    data-testid="secret-update"
                  >
                    {saving ? t('configuration.saving') : t('configuration.show.updateValue')}
                  </Button>
                </div>
              </form>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{t('configuration.show.notFound')}</p>
        )}
      </Card>

      <ConfirmDialog
        open={confirmingDelete}
        onOpenChange={setConfirmingDelete}
        title={t('configuration.deleteDialog.title')}
        description={
          entry ? t('configuration.deleteDialog.description', { key: entry.key }) : undefined
        }
        confirmLabel={t('common.delete')}
        onConfirm={() => void handleDelete()}
      />
    </main>
  );
}

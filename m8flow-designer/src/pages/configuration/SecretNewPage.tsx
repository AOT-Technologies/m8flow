import { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { createSecret, secretsErrorMessage } from '@/lib/secretsApi';

import { ConfigurationGate, useConfigurationContext } from './ConfigurationGate';
import { ConfigurationBackButton } from './ConfigurationBackButton';
import { SecretValueField } from './SecretValueField';

const KEY_PATTERN = /^\w+$/;

export default function SecretNewPage() {
  const { t } = useTranslation();
  return (
    <ConfigurationGate title={t('configuration.new.title')} requireTenant>
      <SecretNewBody />
    </ConfigurationGate>
  );
}

function SecretNewBody() {
  const { t } = useTranslation();
  const { scopedTenantId, canCreateSecrets } = useConfigurationContext();
  const navigate = useNavigate();
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canCreateSecrets) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          <ConfigurationBackButton />
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{t('configuration.new.title')}</h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">{t('configuration.notAllowed')}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('configuration.new.notAllowedBody')}
          </p>
          <Button asChild variant="pill-outline" size="pill" className="mt-4">
            <Link to="/configuration/secrets">{t('configuration.new.backToSecrets')}</Link>
          </Button>
        </Card>
      </main>
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const cleaned = key.trim();
    if (!KEY_PATTERN.test(cleaned) || submitting) {
      if (!KEY_PATTERN.test(cleaned)) {
        setError(t('configuration.validation.keyPattern'));
      }
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createSecret(cleaned, value, scopedTenantId);
      setValue('');
      navigate(`/configuration/secrets/${encodeURIComponent(cleaned)}`);
    } catch (err: unknown) {
      setError(secretsErrorMessage(err, t('configuration.errors.create')));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <ConfigurationBackButton />
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{t('configuration.new.title')}</h1>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          {t('configuration.new.subtitle')}
        </p>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <form onSubmit={(event) => void handleSubmit(event)}>
          <label className="block text-sm font-medium text-foreground">
            {t('configuration.secretKey')}
            <Input
              className="mt-1.5"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              autoComplete="off"
              data-testid="secret-key"
              required
            />
          </label>
          <SecretValueField id="secret-value-input" label={t('configuration.new.value')} value={value} onChange={setValue} />
          {error ? (
            <Alert tone="error" className="mt-3">
              {error}
            </Alert>
          ) : null}
          <div className="mt-6 flex flex-wrap gap-2">
            <Button asChild type="button" variant="pill-cancel" size="pill">
              <Link to="/configuration/secrets">{t('common.cancel')}</Link>
            </Button>
            <Button
              type="submit"
              variant="pill-dark"
              size="pill"
              disabled={!key.trim() || submitting}
              data-testid="secret-create"
            >
              {submitting ? t('configuration.saving') : t('configuration.new.create')}
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
}

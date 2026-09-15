import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { createSecret, secretsErrorMessage } from '@/lib/secretsApi';

import { ConfigurationGate, useConfigurationContext } from './ConfigurationGate';

const TITLE = 'New secret';
const KEY_PATTERN = /^\w+$/;

export default function SecretNewPage() {
  return (
    <ConfigurationGate title={TITLE}>
      <SecretNewBody />
    </ConfigurationGate>
  );
}

function SecretNewBody() {
  const { scopedTenantId, canManageSecrets } = useConfigurationContext();
  const navigate = useNavigate();
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canManageSecrets) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{TITLE}</h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">Not allowed</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Your role can view secrets but cannot create them.
          </p>
          <Button asChild variant="pill-outline" size="pill" className="mt-4">
            <Link to="/configuration/secrets">Back to secrets</Link>
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
        setError('Secret key must be a word (letters, digits, underscore).');
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
      setError(secretsErrorMessage(err, 'Could not create secret.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{TITLE}</h1>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          The value is stored encrypted and will not be shown again after you save.
        </p>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <form onSubmit={(event) => void handleSubmit(event)}>
          <label className="block text-sm font-medium text-foreground">
            Secret key
            <Input
              className="mt-1.5"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              autoComplete="off"
              data-testid="secret-key"
              required
            />
          </label>
          <label className="mt-4 block text-sm font-medium text-foreground">
            Value
            <Input
              className="mt-1.5"
              type="password"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              autoComplete="new-password"
              data-testid="secret-value"
              required
            />
          </label>
          {error ? (
            <Alert tone="error" className="mt-3">
              {error}
            </Alert>
          ) : null}
          <div className="mt-6 flex flex-wrap gap-2">
            <Button asChild type="button" variant="pill-cancel" size="pill">
              <Link to="/configuration/secrets">Cancel</Link>
            </Button>
            <Button
              type="submit"
              variant="pill-dark"
              size="pill"
              disabled={!key.trim() || submitting}
              data-testid="secret-create"
            >
              {submitting ? 'Saving…' : 'Create'}
            </Button>
          </div>
        </form>
      </Card>
    </main>
  );
}

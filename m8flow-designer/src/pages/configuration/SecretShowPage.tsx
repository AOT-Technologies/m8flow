import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  deleteSecret,
  fetchSecret,
  secretsErrorMessage,
  updateSecret,
  type Secret,
} from '@/lib/secretsApi';

import { ConfigurationGate, useConfigurationContext } from './ConfigurationGate';

const TITLE = 'Secret';

export default function SecretShowPage() {
  return (
    <ConfigurationGate title={TITLE}>
      <SecretShowBody />
    </ConfigurationGate>
  );
}

function SecretShowBody() {
  const { key: keyFromRoute } = useParams();
  const { scopedTenantId, canManageSecrets } = useConfigurationContext();
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
    fetchSecret(keyFromRoute, scopedTenantId)
      .then((payload) => {
        if (!cancelled) {
          setEntry(payload);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(secretsErrorMessage(err, 'Could not load secret.'));
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
  }, [keyFromRoute, scopedTenantId]);

  async function handleDelete() {
    if (!entry) {
      return;
    }
    setConfirmingDelete(false);
    setError(null);
    try {
      await deleteSecret(entry.key, scopedTenantId);
      navigate('/configuration/secrets');
    } catch (err: unknown) {
      setError(secretsErrorMessage(err, 'Could not delete secret.'));
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
      await updateSecret(entry.key, draftValue, scopedTenantId);
      setDraftValue('');
      setDraftOpen(false);
      setUpdated(true);
    } catch (err: unknown) {
      setError(secretsErrorMessage(err, 'Could not update secret.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <p className="mb-2 text-sm text-muted-foreground">
          <Link to="/configuration/secrets" className="hover:underline">
            Configuration
          </Link>
        </p>
        <h1 className="font-display text-[32px] font-semibold tracking-tight">
          {entry?.key ?? TITLE}
        </h1>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          The stored value is never shown. Type a new value to replace it.
        </p>
      </div>

      {error ? (
        <Alert tone="error" className="mb-4">
          {error}
        </Alert>
      ) : null}

      {updated ? (
        <Alert tone="success" className="mb-4" data-testid="secret-updated">
          Secret updated.
        </Alert>
      ) : null}

      <Card variant="bordered" className="max-w-lg p-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading secret…</p>
        ) : entry ? (
          <>
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
                  Secret key
                </dt>
                <dd className="mt-1 font-medium" data-testid="secret-show-key">
                  {entry.key}
                </dd>
              </div>
            </dl>
            {canManageSecrets ? (
              <div className="mt-6 flex flex-wrap gap-2">
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
                  Edit value
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmingDelete(true)}>
                  Delete
                </Button>
              </div>
            ) : null}
            {canManageSecrets && draftOpen ? (
              <form className="mt-6" onSubmit={(event) => void handleUpdate(event)}>
                <label className="block text-sm font-medium text-foreground">
                  New value
                  <Input
                    className="mt-1.5"
                    type="password"
                    value={draftValue}
                    onChange={(event) => setDraftValue(event.target.value)}
                    autoComplete="new-password"
                    data-testid="secret-value"
                    required
                  />
                </label>
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
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="pill-dark"
                    size="pill"
                    disabled={!draftValue || saving}
                    data-testid="secret-update"
                  >
                    {saving ? 'Saving…' : 'Update value'}
                  </Button>
                </div>
              </form>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Secret not found.</p>
        )}
      </Card>

      <ConfirmDialog
        open={confirmingDelete}
        onOpenChange={setConfirmingDelete}
        title="Delete secret?"
        description={entry ? `Delete secret "${entry.key}"? This cannot be undone.` : undefined}
        confirmLabel="Delete"
        onConfirm={() => void handleDelete()}
      />
    </main>
  );
}

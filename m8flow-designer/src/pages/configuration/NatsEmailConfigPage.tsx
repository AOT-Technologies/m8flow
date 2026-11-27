import { FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { PasswordInput } from '@/components/ui/password-input';
import {
  createNamedValue,
  fetchNamedValues,
  namedValuesErrorMessage,
  updateNamedValue,
  type NamedValue,
} from '@/lib/namedValuesApi';
import { fetchNatsEmailStatus, secretsErrorMessage, type NatsEmailSecretKey, type NatsEmailStatus } from '@/lib/secretsApi';

import { ConfigurationBackButton } from './ConfigurationBackButton';
import { ConfigurationGate } from './ConfigurationGate';
import { NamedValuesGate, useNamedValuesContext } from './NamedValuesGate';

type FieldKind = 'host' | 'port' | 'email' | 'text' | 'password' | 'boolean';
type FieldId = 'host' | 'port' | 'starttls' | 'ssl' | 'fromEmail' | 'username' | 'password';

/** The NATS_SMTP_* secrets the notification worker reads (external_form_notification_service). */
/** One entry per NATS_EMAIL_SECRET_KEYS name. `default` is what an on/off field starts at
 * on a first-time setup (matches the SMTP connector); it is saved explicitly. */
const FIELDS: { key: NatsEmailSecretKey; id: FieldId; kind: FieldKind; required?: boolean; default?: 'true' | 'false' }[] = [
  { key: 'NATS_SMTP_HOST', id: 'host', kind: 'host', required: true },
  { key: 'NATS_SMTP_PORT', id: 'port', kind: 'port' },
  { key: 'NATS_SMTP_STARTTLS', id: 'starttls', kind: 'boolean', default: 'true' },
  { key: 'NATS_SMTP_SSL', id: 'ssl', kind: 'boolean', default: 'false' },
  { key: 'NATS_SMTP_FROM_EMAIL', id: 'fromEmail', kind: 'email', required: true },
  { key: 'NATS_SMTP_USERNAME', id: 'username', kind: 'text' },
  { key: 'NATS_SMTP_PASSWORD', id: 'password', kind: 'password' },
];

const HOST_RE = /^[A-Za-z0-9.-]+$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+$/;

export default function NatsEmailConfigPage() {
  const { t } = useTranslation();
  return (
    // Reading the status needs /secrets (ConfigurationGate); the settings themselves are
    // configuration variables, so NamedValuesGate also requires a confirmed tenant: a
    // super-admin's selection checked against the tenant list, or the selected-tenant cookie.
    <ConfigurationGate title={t('configuration.natsEmail.page.title')} requireTenant>
      <NamedValuesGate title={t('configuration.natsEmail.page.title')}>
        <NatsEmailConfigBody />
      </NamedValuesGate>
    </ConfigurationGate>
  );
}

function NatsEmailConfigBody() {
  const { t } = useTranslation();
  const { tenantId, isSuperAdmin, canCreateNamedValues, canUpdateNamedValues } = useNamedValuesContext();
  // Same tenant rule as the Configuration variables page: a super-admin passes the checked
  // tenant explicitly; everyone else is scoped by the backend's selected-tenant cookie.
  const scopedTenantId = isSuperAdmin ? tenantId : null;
  // Each field is saved as a sensitive configuration variable: created on first save,
  // updated after that, so editing needs both.
  const canEdit = canCreateNamedValues && canUpdateNamedValues;
  const [status, setStatus] = useState<NatsEmailStatus | null>(null);
  const [variables, setVariables] = useState<NamedValue[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    Promise.all([fetchNatsEmailStatus(scopedTenantId), fetchNamedValues(scopedTenantId)])
      .then(([nextStatus, nextVariables]) => {
        if (cancelled) return;
        setStatus(nextStatus);
        setVariables(nextVariables);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(secretsErrorMessage(err, t('configuration.natsEmail.page.errors.load')));
      });
    return () => {
      cancelled = true;
    };
  }, [scopedTenantId, reloadKey]);

  const stateOf = (key: string): 'saved' | 'unreadable' | 'notSet' =>
    status?.configuredKeys.includes(key) ? 'saved' : status?.unreadableKeys.includes(key) ? 'unreadable' : 'notSet';

  // First-time setup: nothing saved yet, so on/off fields can start at their defaults.
  const freshSetup = !!status && status.configuredKeys.length === 0 && status.unreadableKeys.length === 0;
  // An on/off field without a usable saved value. Once the tenant has settings, start it at
  // off, because that is what the worker uses for a missing key; showing the default (STARTTLS
  // on) would misstate the current behavior and change it on the next save.
  const startValue = (field: (typeof FIELDS)[number]) =>
    field.kind === 'boolean' && stateOf(field.key) !== 'saved' ? (freshSetup ? field.default : 'false') : undefined;

  // What the field holds now: typed input, else the start value for an on/off field.
  const valueOf = (field: (typeof FIELDS)[number]) => values[field.key] ?? startValue(field) ?? '';

  function validate(): Record<string, string> {
    const errors: Record<string, string> = {};
    for (const field of FIELDS) {
      const value = valueOf(field).trim();
      if (!value) {
        // A required key that is already saved may stay blank: blank keeps it.
        if (field.required && stateOf(field.key) !== 'saved') {
          errors[field.key] = t('configuration.natsEmail.page.validation.required');
        }
        continue;
      }
      if (field.kind === 'host' && !HOST_RE.test(value)) {
        errors[field.key] = t('configuration.natsEmail.page.validation.host');
      } else if (field.kind === 'port' && !(/^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 65535)) {
        errors[field.key] = t('configuration.natsEmail.page.validation.port');
      } else if (field.kind === 'email' && !EMAIL_RE.test(value)) {
        errors[field.key] = t('configuration.natsEmail.page.validation.email');
      }
    }
    return errors;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving || !status) return;
    setSaveError(null);
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const changes = FIELDS.flatMap((field) => {
      // Passwords keep their exact value; everything else is trimmed. A whitespace-only
      // password counts as blank, as in validate(): the worker would read it as no password.
      const raw = valueOf(field);
      const value = field.kind === 'password' ? (raw.trim() ? raw : '') : raw.trim();
      return value ? [{ key: field.key, value }] : [];
    });
    if (changes.length === 0) {
      setSaveError(t('configuration.natsEmail.page.nothingToSave'));
      return;
    }

    setSaving(true);
    const saved: string[] = [];
    try {
      for (const { key, value } of changes) {
        // Sensitive, so the value goes straight to the secret provider (Vault when enabled).
        const existing = variables.find((variable) => variable.name.toLowerCase() === key.toLowerCase());
        if (existing) {
          await updateNamedValue(existing.id, { value, is_sensitive: true }, scopedTenantId);
        } else {
          await createNamedValue({ name: key, value, is_sensitive: true }, scopedTenantId);
        }
        saved.push(key);
      }
      // Back to the list, where the NATS_SMTP_* keys now sit with the other variables.
      navigate('/configuration/named-values', { state: { natsEmailSaved: true } });
    } catch (err: unknown) {
      const failed = changes[saved.length]?.key ?? '';
      const message = t('configuration.natsEmail.page.errors.save', {
        key: failed,
        message: namedValuesErrorMessage(err, t('configuration.namedValues.errors.update')),
      });
      // Earlier keys are already stored; say so, or the user may assume nothing changed.
      setSaveError(
        saved.length > 0
          ? `${message} ${t('configuration.natsEmail.page.errors.partial', { keys: saved.join(', ') })}`
          : message,
      );
      // Drop what was saved; keep anything that failed so it can be retried.
      setValues((current) => {
        const next = { ...current };
        for (const key of saved) delete next[key];
        return next;
      });
      setReloadKey((key) => key + 1);
    } finally {
      setSaving(false);
    }
  }

  function renderControl(field: (typeof FIELDS)[number]) {
    const state = stateOf(field.key);
    const id = `nats-email-${field.id}`;
    const value = valueOf(field);
    const common = {
      id,
      disabled: !canEdit || saving,
      'aria-invalid': fieldErrors[field.key] ? true : undefined,
      'data-testid': id,
    };
    const set = (next: string) => setValues((current) => ({ ...current, [field.key]: next }));
    if (field.kind === 'boolean') {
      return (
        <select
          {...common}
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={value}
          onChange={(event) => set(event.target.value)}
        >
          {/* Only a readable saved value can be kept; an unreadable one must be replaced. */}
          {state === 'saved' ? <option value="">{t('configuration.natsEmail.page.keep')}</option> : null}
          <option value="true">
            {t(freshSetup && field.default === 'true' ? 'configuration.natsEmail.page.onDefault' : 'configuration.natsEmail.page.on')}
          </option>
          <option value="false">
            {t(freshSetup && field.default === 'false' ? 'configuration.natsEmail.page.offDefault' : 'configuration.natsEmail.page.off')}
          </option>
        </select>
      );
    }
    const placeholder = state === 'notSet' ? undefined : t('configuration.natsEmail.page.keepHint');
    if (field.kind === 'password') {
      return (
        <PasswordInput
          {...common}
          toggleLabel={t('configuration.natsEmail.page.fields.password.label')}
          value={value}
          placeholder={placeholder}
          autoComplete="new-password"
          onChange={(event) => set(event.target.value)}
        />
      );
    }
    return (
      <Input
        {...common}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        inputMode={field.kind === 'port' ? 'numeric' : undefined}
        onChange={(event) => set(event.target.value)}
      />
    );
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <ConfigurationBackButton label={t('configuration.namedValues.title')} to="/configuration/named-values" />
        <h1 className="font-display text-[32px] font-semibold tracking-tight">
          {t('configuration.natsEmail.page.title')}
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('configuration.natsEmail.page.subtitle')}</p>
      </div>

      {loadError ? (
        <Alert tone="error" className="mb-4">
          {loadError}
        </Alert>
      ) : null}
      {status && status.waitingCount > 0 ? (
        <Alert tone="warning" className="mb-4" data-testid="nats-email-waiting">
          {t('configuration.natsEmail.waiting', { count: status.waitingCount })}
        </Alert>
      ) : null}
      {status && !canEdit ? (
        <Alert tone="info" className="mb-4">
          {t('configuration.natsEmail.page.readOnly')}
        </Alert>
      ) : null}

      {status ? (
        <Card variant="bordered" className="max-w-2xl p-6">
          <form noValidate onSubmit={(event) => void handleSubmit(event)} className="space-y-5">
            {FIELDS.map((field) => {
              const state = stateOf(field.key);
              const help = t(`configuration.natsEmail.page.fields.${field.id}.help`);
              return (
                <div key={field.key}>
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <label htmlFor={`nats-email-${field.id}`} className="text-sm font-medium text-foreground">
                      {t(`configuration.natsEmail.page.fields.${field.id}.label`)}
                      {field.required ? <span className="text-destructive"> *</span> : null}
                    </label>
                    <code className="font-mono text-[11px] text-muted-foreground">{field.key}</code>
                    {state !== 'notSet' ? (
                      <Badge
                        variant={state === 'saved' ? 'success' : 'warning'}
                        data-testid={`nats-email-state-${field.id}`}
                      >
                        {t(`configuration.natsEmail.page.state.${state}`)}
                      </Badge>
                    ) : null}
                  </div>
                  {renderControl(field)}
                  {fieldErrors[field.key] ? (
                    <p className="mt-1 text-xs text-destructive">{fieldErrors[field.key]}</p>
                  ) : help ? (
                    <p className="mt-1 text-xs text-muted-foreground">{help}</p>
                  ) : null}
                </div>
              );
            })}

            {saveError ? <Alert tone="error">{saveError}</Alert> : null}

            {canEdit ? (
              <div className="flex flex-wrap gap-2">
                <Button type="submit" variant="pill-dark" size="pill" disabled={saving} data-testid="nats-email-save">
                  {saving ? t('configuration.saving') : t('configuration.natsEmail.page.save')}
                </Button>
              </div>
            ) : null}
          </form>
        </Card>
      ) : null}
    </main>
  );
}

import { Eye, EyeOff } from 'lucide-react';
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useBeforeUnload, useBlocker, useNavigate, useParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ApiError } from '@/lib/api';
import {
  connectorsErrorMessage,
  createConnectorProfile,
  fetchConnectorProfile,
  fetchConnectorProfiles,
  fetchConnectorTemplate,
  updateConnectorProfile,
  type ConnectorFieldDescriptor,
  type ConnectorProfile,
  type ConnectorTemplate,
} from '@/lib/connectorsApi';

import { ConnectorsGate, useConnectorsContext } from './ConnectorsGate';

const IDENTIFIER_MAX = 64;
const SECTION_ORDER = ['connection', 'authentication'];

/** Lowercase letters, digits and single hyphens, e.g. "Slack – Prod!" -> "slack-prod". */
export function slugifyIdentifier(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, IDENTIFIER_MAX)
    .replace(/-+$/, '');
}

/** Only `type: "password"` fields are masked; other profile fields are stored
 * encrypted too but are not credentials (host, port, instance URL…). */
function isMasked(field: ConnectorFieldDescriptor) {
  return field.type === 'password';
}

export function connectorFieldError(
  field: ConnectorFieldDescriptor,
  raw: string,
  configured: boolean,
): string | null {
  const value = raw.trim();
  if (!value) {
    return field.required && !configured ? `${field.label} is required.` : null;
  }
  if (field.type === 'url') {
    let ok = false;
    try {
      ok = ['http:', 'https:'].includes(new URL(value).protocol);
    } catch {
      ok = false;
    }
    if (!ok) {
      return 'Enter a full URL starting with http:// or https://.';
    }
  }
  if (field.type === 'port' && !(/^\d+$/.test(value) && +value >= 1 && +value <= 65535)) {
    return 'Enter a port number between 1 and 65535.';
  }
  if (field.type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    return 'Enter a valid email address.';
  }
  if (field.pattern) {
    let matches = true;
    try {
      matches = new RegExp(field.pattern).test(value);
    } catch {
      // A malformed template pattern must not block saving. The backend does not
      // re-check patterns, so the template tests are the real guard; log so a
      // broken template is visible rather than silently unvalidated.
      console.warn(`Ignoring invalid pattern for connector field "${field.id}": ${field.pattern}`);
    }
    if (!matches) {
      return field.patternMessage ?? `Enter a valid ${field.label.toLowerCase()}.`;
    }
  }
  return null;
}

function withoutKeys(errors: Record<string, string>, ...keys: string[]) {
  const next = { ...errors };
  for (const key of keys) {
    delete next[key];
  }
  return next;
}

function stripeKeyMode(value: string): 'test' | 'live' | null {
  const match = /^(?:sk|rk)_(test|live)_/.exec(value.trim());
  return match ? (match[1] as 'test' | 'live') : null;
}

function RouterLink({ href, className, children }: BreadcrumbLinkProps) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

/** Confirms before leaving a dirty form: every router navigation (links,
 * navigate(), browser Back/Forward) plus tab close/reload. */
function useUnsavedChangesGuard(dirty: boolean) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty &&
      // Same page (self link or hash-only): nothing is left behind, so no prompt.
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );
  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (dirty) {
          event.preventDefault();
          event.returnValue = '';
        }
      },
      [dirty],
    ),
  );

  return (
    <ConfirmDialog
      open={blocker.state === 'blocked'}
      onOpenChange={(open) => {
        if (!open) {
          blocker.reset?.();
        }
      }}
      // Passing `pending` stops the dialog closing itself on confirm: that close
      // would call reset() right after proceed() and cancel the navigation.
      // proceed() alone moves the blocker out of 'blocked', which closes it.
      pending={false}
      title="Discard unsaved changes?"
      description="You have changes to this profile that have not been saved."
      cancelLabel="Keep editing"
      confirmLabel="Discard changes"
      onConfirm={() => blocker.proceed?.()}
    />
  );
}

function FormField({
  id,
  label,
  required,
  help,
  error,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  help?: ReactNode;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="mt-4 first:mt-0">
      <label htmlFor={id} className="block text-sm font-medium text-foreground">
        {label}
        {required ? (
          <span className="ml-0.5 text-destructive" aria-hidden>
            *
          </span>
        ) : (
          <span className="ml-1 font-normal text-muted-foreground">(optional)</span>
        )}
      </label>
      <div className="mt-1.5">{children}</div>
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-[13px] text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      {help ? (
        <p id={`${id}-help`} className="mt-1.5 text-[13px] text-muted-foreground">
          {help}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(id: string, error?: string | null, help?: ReactNode) {
  return [error ? `${id}-error` : null, help ? `${id}-help` : null].filter(Boolean).join(' ') || undefined;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="mt-7 first:mt-0">
      <legend className="mb-3 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

export default function ConnectorProfileEditPage() {
  const { profileId } = useParams();
  return (
    <ConnectorsGate title={profileId ? 'Edit profile' : 'Add profile'} requireTenant>
      <ConnectorProfileEditBody />
    </ConnectorsGate>
  );
}

function ConnectorProfileEditBody() {
  const { connectorId = '', profileId } = useParams();
  const isEdit = Boolean(profileId);
  const navigate = useNavigate();
  const { scopedTenantId, canManageConnectorProfiles } = useConnectorsContext();
  const listPath = `/connectors/${encodeURIComponent(connectorId)}/profiles`;

  const [template, setTemplate] = useState<ConnectorTemplate | null>(null);
  const [existing, setExisting] = useState<ConnectorProfile | null>(null);
  const [takenNames, setTakenNames] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [initialSnapshot, setInitialSnapshot] = useState<string | null>(null);

  const connectorName = template?.name ?? 'connector';
  const title = isEdit ? `Edit ${connectorName} profile` : `Add ${connectorName} profile`;
  const identifier = isEdit ? (existing?.profile_name ?? '') : slugifyIdentifier(displayName);
  const snapshot = JSON.stringify({ displayName, description, values });
  const dirty = initialSnapshot !== null && snapshot !== initialSnapshot && !saving;
  const leaveDialog = useUnsavedChangesGuard(dirty);

  useEffect(() => {
    if (!canManageConnectorProfiles) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const load = async () => {
      const [loadedTemplate, loadedProfile, siblings] = await Promise.all([
        fetchConnectorTemplate(connectorId),
        isEdit && profileId ? fetchConnectorProfile(Number(profileId), scopedTenantId) : null,
        // Duplicate pre-check only; the backend's 409 stays authoritative.
        isEdit
          ? []
          : fetchConnectorProfiles({ connectorType: connectorId, tenantId: scopedTenantId }).catch(
              () => [],
            ),
      ]);
      if (cancelled) {
        return;
      }
      const loadedDisplayName = loadedProfile?.display_name ?? '';
      const loadedDescription = loadedProfile?.description ?? '';
      // Stored values are secrets and never come back, so inputs start empty.
      const loadedValues = { ...(loadedProfile?.config ?? {}) };
      setTemplate(loadedTemplate);
      setExisting(loadedProfile);
      setTakenNames(new Set(siblings.map((profile) => profile.profile_name)));
      setDisplayName(loadedDisplayName);
      setDescription(loadedDescription);
      setValues(loadedValues);
      setInitialSnapshot(
        JSON.stringify({
          displayName: loadedDisplayName,
          description: loadedDescription,
          values: loadedValues,
        }),
      );
    };
    load()
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(connectorsErrorMessage(err, 'Could not load the profile form.'));
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
  }, [canManageConnectorProfiles, connectorId, isEdit, profileId, scopedTenantId]);

  const fields = useMemo(() => template?.profileFields ?? [], [template]);
  const sections = useMemo(() => {
    const labels = new Map((template?.groups ?? []).map((group) => [group.id, group.label]));
    const ids = [...new Set(fields.map((field) => field.group || 'authentication'))].sort(
      (a, b) => (SECTION_ORDER.indexOf(a) + 1 || 99) - (SECTION_ORDER.indexOf(b) + 1 || 99),
    );
    return ids.map((id) => ({
      id,
      label: labels.get(id) || id.charAt(0).toUpperCase() + id.slice(1),
      fields: fields.filter((field) => (field.group || 'authentication') === id),
    }));
  }, [template, fields]);

  const breadcrumbs = (
    <Breadcrumbs
      className="mb-3"
      LinkComponent={RouterLink}
      linkClassName="text-info font-semibold"
      items={[
        { label: 'Connectors', href: '/connectors' },
        { label: template?.name ? `${template.name} profiles` : 'Connector profiles', href: listPath },
        { label: isEdit ? 'Edit profile' : 'Add profile' },
      ]}
    />
  );

  if (!canManageConnectorProfiles) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          {breadcrumbs}
          <h1 className="font-display text-[32px] font-semibold tracking-tight">
            {isEdit ? 'Edit profile' : 'Add profile'}
          </h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">Not allowed</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Your role can open Connectors but cannot create or edit a profile.
          </p>
          <Button asChild variant="pill-outline" size="pill" className="mt-4">
            <Link to={listPath}>Back to profiles</Link>
          </Button>
        </Card>
      </main>
    );
  }

  function isConfigured(field: ConnectorFieldDescriptor) {
    return Boolean(existing?.configured_secrets.includes(field.id));
  }

  function identifierError(): string | null {
    if (isEdit) {
      return null;
    }
    if (!identifier) {
      return displayName.trim()
        ? 'The display name must contain at least one letter or number.'
        : null;
    }
    if (takenNames.has(identifier)) {
      return `A profile with the identifier "${identifier}" already exists. Choose a different display name.`;
    }
    return null;
  }

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!displayName.trim()) {
      next.displayName = 'Display name is required.';
    }
    const idError = identifierError();
    if (idError) {
      next.identifier = idError;
    }
    for (const field of fields) {
      const message = connectorFieldError(field, values[field.id] ?? '', isConfigured(field));
      if (message) {
        next[field.id] = message;
      }
    }
    return next;
  }

  function setValue(fieldId: string, value: string) {
    setValues((prev) => ({ ...prev, [fieldId]: value }));
    setFieldErrors((prev) => withoutKeys(prev, fieldId));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving) {
      return;
    }
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setError('Fix the highlighted fields and try again.');
      const firstId = Object.keys(errors)[0];
      document.getElementById(`connector-profile-input-${firstId}`)?.focus();
      return;
    }
    setSaving(true);
    setError(null);
    const config: Record<string, string> = {};
    for (const field of fields) {
      const raw = (values[field.id] ?? '').trim();
      if (raw !== '') {
        config[field.id] = raw;
      }
    }
    try {
      if (isEdit && profileId) {
        await updateConnectorProfile(
          Number(profileId),
          { display_name: displayName.trim(), description: description.trim() || null, config },
          scopedTenantId,
        );
      } else {
        await createConnectorProfile(
          {
            connector_type: connectorId,
            profile_name: identifier,
            display_name: displayName.trim(),
            description: description.trim() || null,
            config,
          },
          scopedTenantId,
        );
      }
      setInitialSnapshot(snapshot);
      navigate(listPath);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setTakenNames((prev) => new Set(prev).add(identifier));
        setFieldErrors({
          identifier: connectorsErrorMessage(err, 'This identifier is already in use.'),
        });
      }
      setError(connectorsErrorMessage(err, 'Could not save the profile.'));
    } finally {
      setSaving(false);
    }
  }

  const liveIdentifierError = fieldErrors.identifier ?? identifierError();
  const identifierInputId = 'connector-profile-input-identifier';
  const displayNameInputId = 'connector-profile-input-displayName';
  const descriptionInputId = 'connector-profile-input-description';

  function renderField(field: ConnectorFieldDescriptor) {
    const inputId = `connector-profile-input-${field.id}`;
    const configured = isConfigured(field);
    const fieldError = fieldErrors[field.id];
    const value = values[field.id] ?? '';
    const stripeMode = connectorId === 'stripe' && field.id === 'api_key' ? stripeKeyMode(value) : null;
    const help = (
      <>
        {configured ? 'A value is saved. Leave blank to keep it. ' : null}
        {field.helpText}
      </>
    );
    const hasHelp = configured || Boolean(field.helpText);
    const common = {
      id: inputId,
      'aria-invalid': fieldError ? true : undefined,
      'aria-describedby': describedBy(inputId, fieldError, hasHelp ? help : null),
      'data-testid': `connector-profile-field-${field.id}`,
    };

    let control: ReactNode;
    if (field.type === 'boolean') {
      control = (
        <select
          {...common}
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={value}
          onChange={(event) => setValue(field.id, event.target.value)}
        >
          <option value="">{configured ? 'Keep current setting' : 'Off (default)'}</option>
          <option value="true">On</option>
          {configured ? <option value="false">Off</option> : null}
        </select>
      );
    } else if (isMasked(field)) {
      const shown = Boolean(visible[field.id]);
      control = (
        <div className="relative">
          <Input
            {...common}
            className="pr-9"
            type={shown ? 'text' : 'password'}
            value={value}
            onChange={(event) => setValue(field.id, event.target.value)}
            autoComplete="new-password"
            spellCheck={false}
            placeholder={configured ? '••••••••' : field.example}
          />
          <button
            type="button"
            className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-lg text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
            aria-label={shown ? `Hide ${field.label.toLowerCase()}` : `Show ${field.label.toLowerCase()}`}
            aria-pressed={shown}
            onClick={() => setVisible((prev) => ({ ...prev, [field.id]: !prev[field.id] }))}
          >
            {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
          </button>
        </div>
      );
    } else {
      control = (
        <Input
          {...common}
          type={field.type === 'url' ? 'url' : field.type === 'email' ? 'email' : 'text'}
          inputMode={field.type === 'port' ? 'numeric' : undefined}
          value={value}
          onChange={(event) => setValue(field.id, event.target.value)}
          autoComplete="off"
          spellCheck={false}
          placeholder={field.example}
        />
      );
    }

    return (
      <FormField
        key={field.id}
        id={inputId}
        label={field.label}
        required={field.required && !configured}
        error={fieldError}
        help={hasHelp ? help : null}
      >
        {control}
        {stripeMode ? (
          <Alert
            tone={stripeMode === 'live' ? 'warning' : 'info'}
            className="mt-2 py-2 text-[13px]"
            data-testid="stripe-key-mode"
          >
            {stripeMode === 'live'
              ? 'Live mode key. Payments made with this profile are real.'
              : 'Test mode key. No real money moves.'}
          </Alert>
        ) : null}
      </FormField>
    );
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        {breadcrumbs}
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          {isEdit
            ? 'Stored secret values are never shown. Leave a secret blank to keep its current value.'
            : 'Secret values are encrypted when saved and are never shown again.'}
        </p>
      </div>

      {error ? (
        <Alert tone="error" className="mb-4 max-w-lg" role="alert">
          {error}
        </Alert>
      ) : null}

      <Card variant="bordered" className="max-w-lg overflow-visible p-6 pb-0">
        {loading ? (
          <p className="pb-6 text-sm text-muted-foreground">Loading profile…</p>
        ) : (
          <form noValidate onSubmit={(event) => void handleSubmit(event)}>
            <p className="mb-5 text-[13px] text-muted-foreground">
              Fields marked <span className="text-destructive">*</span> are required.
            </p>
            <Section title="Profile details">
              <FormField
                id={displayNameInputId}
                label="Display name"
                required
                error={fieldErrors.displayName}
              >
                <Input
                  id={displayNameInputId}
                  value={displayName}
                  onChange={(event) => {
                    setDisplayName(event.target.value);
                    setFieldErrors((prev) => withoutKeys(prev, 'displayName', 'identifier'));
                  }}
                  autoComplete="off"
                  placeholder={`e.g. ${connectorName} production`}
                  aria-invalid={fieldErrors.displayName ? true : undefined}
                  aria-describedby={describedBy(displayNameInputId, fieldErrors.displayName)}
                  data-testid="connector-profile-display-name"
                />
              </FormField>
              <FormField
                id={identifierInputId}
                label="Identifier"
                required
                error={liveIdentifierError}
                help={
                  isEdit
                    ? 'Service Tasks select this profile by its identifier. It cannot be changed.'
                    : 'Generated from the display name. Service Tasks select this profile by it, and it cannot be changed later.'
                }
              >
                <Input
                  id={identifierInputId}
                  value={identifier}
                  readOnly
                  tabIndex={-1}
                  className="bg-muted/50 font-mono text-muted-foreground"
                  placeholder="Generated from the display name"
                  aria-invalid={liveIdentifierError ? true : undefined}
                  aria-describedby={describedBy(identifierInputId, liveIdentifierError, true)}
                  data-testid="connector-profile-name"
                />
              </FormField>
              <FormField id={descriptionInputId} label="Description">
                <Textarea
                  id={descriptionInputId}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                  placeholder="What this profile is for, e.g. which environment it targets."
                  data-testid="connector-profile-description"
                />
              </FormField>
            </Section>

            {sections.map((section) => (
              <Section key={section.id} title={section.label}>
                {section.fields.map(renderField)}
              </Section>
            ))}

            <div className="sticky bottom-0 -mx-6 mt-7 flex flex-wrap gap-2 rounded-b-[inherit] border-t border-border bg-card px-6 py-4">
              <Button
                asChild
                type="button"
                variant="pill-cancel"
                size="pill"
                className="tracking-normal normal-case"
              >
                <Link to={listPath}>Cancel</Link>
              </Button>
              <Button
                type="submit"
                variant="pill-dark"
                size="pill"
                className="tracking-normal normal-case"
                disabled={saving}
                data-testid="connector-profile-save"
              >
                {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Save profile'}
              </Button>
            </div>
          </form>
        )}
      </Card>
      {leaveDialog}
    </main>
  );
}

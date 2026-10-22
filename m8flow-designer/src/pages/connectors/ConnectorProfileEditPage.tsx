import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Link, useBeforeUnload, useBlocker, useNavigate, useParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { PasswordInput } from '@/components/ui/password-input';
import { Textarea } from '@/components/ui/textarea';
import i18n from '@/i18n';
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

const IDENTIFIER_MIN = 3;
const IDENTIFIER_MAX = 50;
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

export const DISPLAY_NAME_HINT =
  'Use letters, numbers, spaces, - _ . ( ). Must start with a letter or number.';

/** Same rules as the backend's `_display_name_error`. */
export function displayNameError(raw: string): string | null {
  const value = raw.trim();
  if (!value) {
    return 'Display name is required.';
  }
  // Code points, like Python's len(); .length would count astral letters twice.
  const length = [...value].length;
  if (length < 3 || length > 60) {
    return 'Display name must be 3-60 characters.';
  }
  return /^[\p{L}\p{N}][\p{L}\p{N}_ .()-]*$/u.test(value) ? null : DISPLAY_NAME_HINT;
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
    return field.required && !configured
      ? i18n.t('connectors.validation.required', { label: field.label })
      : null;
  }
  if (field.type === 'url') {
    let ok = false;
    try {
      ok = ['http:', 'https:'].includes(new URL(value).protocol);
    } catch {
      ok = false;
    }
    if (!ok) {
      return i18n.t('connectors.validation.url');
    }
  }
  if (field.type === 'port' && !(/^\d+$/.test(value) && +value >= 1 && +value <= 65535)) {
    return i18n.t('connectors.validation.port');
  }
  if (field.type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    return i18n.t('connectors.validation.email');
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
      return (
        field.patternMessage ??
        i18n.t('connectors.validation.pattern', { label: field.label.toLowerCase() })
      );
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
  const { t } = useTranslation();
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
      title={t('connectors.edit.unsaved.title')}
      description={t('connectors.edit.unsaved.description')}
      cancelLabel={t('connectors.edit.unsaved.keepEditing')}
      confirmLabel={t('connectors.edit.unsaved.discard')}
      onConfirm={() => blocker.proceed?.()}
    />
  );
}

type FieldStatus = 'configured' | 'not-set' | 'clearing';

const STATUS_BADGE: Record<FieldStatus, { label: string; variant: 'success' | 'outline' | 'warning' }> = {
  configured: { label: 'Configured', variant: 'success' },
  'not-set': { label: 'Not set', variant: 'outline' },
  clearing: { label: 'Will be cleared', variant: 'warning' },
};

function FormField({
  id,
  label,
  required,
  status,
  help,
  error,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  status?: FieldStatus;
  help?: ReactNode;
  error?: string | null;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="mt-4 first:mt-0">
      <label htmlFor={id} className="flex items-center text-sm font-medium text-foreground">
        {label}
        {required ? (
          <span className="ml-0.5 text-destructive" aria-hidden>
            *
          </span>
        ) : (
          <span className="ml-1 font-normal text-muted-foreground">{t('connectors.edit.optional')}</span>
        )}
        {status ? (
          <Badge
            variant={STATUS_BADGE[status].variant}
            className="ml-auto"
            data-testid={`${id}-status`}
          >
            {STATUS_BADGE[status].label}
          </Badge>
        ) : null}
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
  const { t } = useTranslation();
  const { profileId } = useParams();
  return (
    <ConnectorsGate
      title={profileId ? t('connectors.editProfile') : t('connectors.addProfile')}
      requireTenant
    >
      <ConnectorProfileEditBody />
    </ConnectorsGate>
  );
}

function ConnectorProfileEditBody() {
  const { t } = useTranslation();
  const { connectorId = '', profileId } = useParams();
  const isEdit = Boolean(profileId);
  const navigate = useNavigate();
  const { scopedTenantId, canCreateConnectorProfiles, canUpdateConnectorProfiles } = useConnectorsContext();
  const canWriteProfile = (isEdit ? canUpdateConnectorProfiles : canCreateConnectorProfiles);
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
  const [replacing, setReplacing] = useState<Record<string, boolean>>({});
  const [cleared, setCleared] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [initialSnapshot, setInitialSnapshot] = useState<string | null>(null);

  const connectorName = template?.name ?? t('connectors.edit.connectorFallback');
  const title = isEdit
    ? t('connectors.edit.titleEdit', { name: connectorName })
    : t('connectors.edit.titleAdd', { name: connectorName });
  const identifier = isEdit ? (existing?.profile_name ?? '') : slugifyIdentifier(displayName);
  // Names saved before the rules existed keep working until changed.
  const keepsSavedName = isEdit && displayName.trim() === existing?.display_name;
  const legacyName = keepsSavedName && displayNameError(displayName) !== null;
  const snapshot = JSON.stringify({ displayName, description, values, cleared });
  const dirty = initialSnapshot !== null && snapshot !== initialSnapshot && !saving;
  const leaveDialog = useUnsavedChangesGuard(dirty);

  useEffect(() => {
    if (!canWriteProfile) {
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
      // Saved non-sensitive settings come back in `config` and prefill the
      // form; credentials never do, so their inputs start empty.
      const loadedValues = { ...(loadedProfile?.config ?? {}) };
      setTemplate(loadedTemplate);
      setExisting(loadedProfile);
      setTakenNames(new Set(siblings.map((profile) => profile.profile_name)));
      setDisplayName(loadedDisplayName);
      setDescription(loadedDescription);
      setValues(loadedValues);
      // A fresh form for this profile: the snapshot below records no pending clears.
      setCleared([]);
      setReplacing({});
      setInitialSnapshot(
        JSON.stringify({
          displayName: loadedDisplayName,
          description: loadedDescription,
          values: loadedValues,
          cleared: [],
        }),
      );
    };
    load()
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(connectorsErrorMessage(err, t('connectors.errors.loadForm')));
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
  }, [canWriteProfile, connectorId, isEdit, profileId, scopedTenantId]);

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
        { label: t('connectors.title'), href: '/connectors' },
        {
          label: template?.name
            ? t('connectors.profilesNamed', { name: template.name })
            : t('connectors.profilesTitle'),
          href: listPath,
        },
        { label: isEdit ? t('connectors.editProfile') : t('connectors.addProfile') },
      ]}
    />
  );

  if (!canWriteProfile) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          {breadcrumbs}
          <h1 className="font-display text-[32px] font-semibold tracking-tight">
            {isEdit ? t('connectors.editProfile') : t('connectors.addProfile')}
          </h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">{t('connectors.notAllowed')}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('connectors.edit.notAllowedBody')}
          </p>
          <Button asChild variant="pill-outline" size="pill" className="mt-4">
            <Link to={listPath}>{t('connectors.edit.backToProfiles')}</Link>
          </Button>
        </Card>
      </main>
    );
  }

  function isConfigured(field: ConnectorFieldDescriptor) {
    return Boolean(existing?.configured_secrets.includes(field.id));
  }

  function identifierError(): string | null {
    // An invalid display name already has its own error.
    if (isEdit || displayNameError(displayName)) {
      return null;
    }
    if (identifier.length < IDENTIFIER_MIN) {
      return t('connectors.validation.identifierTooShort', { min: IDENTIFIER_MIN });
    }
    if (takenNames.has(identifier)) {
      return t('connectors.validation.identifierTaken', { identifier });
    }
    return null;
  }

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    const nameError = keepsSavedName ? null : displayNameError(displayName);
    if (nameError) {
      next.displayName = nameError;
    }
    const idError = identifierError();
    if (idError) {
      next.identifier = idError;
    }
    for (const field of fields) {
      const value = values[field.id] ?? '';
      // A cleared or untouched saved value is not sent, so it is not re-checked.
      if (cleared.includes(field.id) || value === existing?.config[field.id]) {
        continue;
      }
      const message = connectorFieldError(field, value, isConfigured(field));
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

  function resetValue(fieldId: string) {
    setValues((prev) => {
      const next = withoutKeys(prev, fieldId);
      const saved = existing?.config[fieldId];
      return saved === undefined ? next : { ...next, [fieldId]: saved };
    });
    setFieldErrors((prev) => withoutKeys(prev, fieldId));
  }

  function setReplace(fieldId: string, on: boolean) {
    setReplacing((prev) => ({ ...prev, [fieldId]: on }));
    if (!on) {
      resetValue(fieldId);
    }
  }

  function setClear(fieldId: string, on: boolean) {
    setCleared((prev) => (on ? [...prev, fieldId] : prev.filter((id) => id !== fieldId)));
    setReplacing((prev) => ({ ...prev, [fieldId]: false }));
    resetValue(fieldId);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving) {
      return;
    }
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setError(t('connectors.validation.fixFields'));
      const firstId = Object.keys(errors)[0];
      document.getElementById(`connector-profile-input-${firstId}`)?.focus();
      return;
    }
    setSaving(true);
    setError(null);
    // Only new or changed values are sent. Blank keeps the saved value; only
    // the Clear button removes one, so a stray delete can't wipe it.
    const config: Record<string, string> = {};
    for (const field of fields) {
      const raw = (values[field.id] ?? '').trim();
      if (raw !== '' && raw !== existing?.config[field.id] && !cleared.includes(field.id)) {
        config[field.id] = raw;
      }
    }
    try {
      if (isEdit && profileId) {
        await updateConnectorProfile(
          Number(profileId),
          {
            display_name: displayName.trim(),
            description: description.trim() || null,
            config,
            ...(cleared.length ? { clear: cleared } : {}),
          },
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
          identifier: connectorsErrorMessage(err, t('connectors.validation.identifierInUse')),
        });
      }
      setError(connectorsErrorMessage(err, t('connectors.errors.saveProfile')));
    } finally {
      setSaving(false);
    }
  }

  const liveIdentifierError = fieldErrors.identifier ?? identifierError();
  const identifierInputId = 'connector-profile-input-identifier';
  const displayNameInputId = 'connector-profile-input-displayName';
  const descriptionInputId = 'connector-profile-input-description';
  const displayNameHelp = `3-60 characters. ${DISPLAY_NAME_HINT}`;

  function renderField(field: ConnectorFieldDescriptor) {
    const inputId = `connector-profile-input-${field.id}`;
    const configured = isConfigured(field);
    const isCleared = cleared.includes(field.id);
    const masked = isMasked(field);
    // A saved credential is replaced, never shown: no input until Replace.
    const hideSecret = masked && configured && !replacing[field.id];
    const fieldError = fieldErrors[field.id];
    const value = values[field.id] ?? '';
    const stripeMode = connectorId === 'stripe' && field.id === 'api_key' ? stripeKeyMode(value) : null;
    const keepHint = configured && !isCleared && !hideSecret && !value.trim();
    const help = (
      <>
        {keepHint ? `${t('connectors.edit.valueSaved')} ` : null}
        {field.helpText}
      </>
    );
    const hasHelp = keepHint || Boolean(field.helpText);
    const placeholder = field.example ? `e.g. ${field.example}` : undefined;
    const common = {
      id: inputId,
      'aria-invalid': fieldError ? true : undefined,
      'aria-describedby': describedBy(inputId, fieldError, hasHelp ? help : null),
      'data-testid': `connector-profile-field-${field.id}`,
    };
    const actionButton = (label: string, onClick: () => void) => (
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label={`${label} ${field.label.toLowerCase()}`}
        onClick={onClick}
      >
        {label}
      </Button>
    );
    const actions = isEdit ? (
      <div className="mt-1.5 flex flex-wrap gap-1.5 empty:hidden">
        {hideSecret ? actionButton('Replace', () => setReplace(field.id, true)) : null}
        {masked && configured && replacing[field.id]
          ? actionButton('Cancel', () => setReplace(field.id, false))
          : null}
        {configured && !field.required ? actionButton('Clear', () => setClear(field.id, true)) : null}
      </div>
    ) : null;

    let control: ReactNode;
    if (isCleared) {
      control = (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-dashed border-input px-3 py-1 text-sm text-muted-foreground">
          Will be removed when you save.
          {actionButton('Undo', () => setClear(field.id, false))}
        </div>
      );
    } else if (hideSecret) {
      control = null;
    } else if (field.type === 'boolean') {
      control = (
        <select
          {...common}
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={value}
          onChange={(event) => setValue(field.id, event.target.value)}
        >
          <option value="">
            {configured ? t('connectors.edit.keepCurrentSetting') : t('connectors.edit.offDefault')}
          </option>
          <option value="true">{t('connectors.edit.on')}</option>
          {configured ? <option value="false">{t('connectors.edit.off')}</option> : null}
        </select>
      );
    } else if (masked) {
      control = (
        <PasswordInput
          {...common}
          toggleLabel={field.label.toLowerCase()}
          value={value}
          onChange={(event) => setValue(field.id, event.target.value)}
          autoComplete="new-password"
          spellCheck={false}
          // Only mounts for a saved credential after Replace is pressed.
          autoFocus={configured}
          placeholder={configured ? t('connectors.edit.enterNewValue') : placeholder}
        />
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
          placeholder={placeholder}
        />
      );
    }

    return (
      <FormField
        key={field.id}
        id={inputId}
        label={field.label}
        required={field.required && !configured}
        status={isEdit ? (isCleared ? 'clearing' : configured ? 'configured' : 'not-set') : undefined}
        error={fieldError}
        help={hasHelp ? help : null}
      >
        {control}
        {isCleared ? null : actions}
        {stripeMode ? (
          <Alert
            tone={stripeMode === 'live' ? 'warning' : 'info'}
            className="mt-2 py-2 text-[13px]"
            data-testid="stripe-key-mode"
          >
            {stripeMode === 'live'
              ? t('connectors.edit.stripeLive')
              : t('connectors.edit.stripeTest')}
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
            ? t('connectors.edit.subtitleEdit')
            : t('connectors.edit.subtitleAdd')}
        </p>
      </div>

      {error ? (
        <Alert tone="error" className="mb-4 max-w-lg" role="alert">
          {error}
        </Alert>
      ) : null}

      <Card variant="bordered" className="max-w-lg overflow-visible p-6 pb-0">
        {loading ? (
          <p className="pb-6 text-sm text-muted-foreground">{t('connectors.edit.loading')}</p>
        ) : (
          <form noValidate onSubmit={(event) => void handleSubmit(event)}>
            <p className="mb-5 text-[13px] text-muted-foreground">
              <Trans
                i18nKey="connectors.edit.requiredNote"
                components={{ req: <span className="text-destructive" /> }}
              />
            </p>
            <Section title={t('connectors.edit.detailsSection')}>
              <FormField
                id={displayNameInputId}
                label={t('connectors.edit.displayName')}
                required
                error={fieldErrors.displayName}
                help={displayNameHelp}
              >
                <Input
                  id={displayNameInputId}
                  value={displayName}
                  onChange={(event) => {
                    setDisplayName(event.target.value);
                    setFieldErrors((prev) => withoutKeys(prev, 'displayName', 'identifier'));
                  }}
                  autoComplete="off"
                  placeholder={t('connectors.edit.displayNamePlaceholder', { name: connectorName })}
                  aria-invalid={fieldErrors.displayName ? true : undefined}
                  aria-describedby={describedBy(displayNameInputId, fieldErrors.displayName, displayNameHelp)}
                  data-testid="connector-profile-display-name"
                />
                {legacyName ? (
                  <Alert
                    tone="warning"
                    className="mt-2 py-2 text-[13px]"
                    data-testid="connector-profile-legacy-name"
                  >
                    This name doesn&apos;t meet the current naming rules. Rename it when you can.
                  </Alert>
                ) : null}
              </FormField>
              <FormField
                id={identifierInputId}
                label={t('connectors.identifier')}
                required
                error={liveIdentifierError}
                help={
                  isEdit
                    ? t('connectors.edit.identifierHelpEdit')
                    : t('connectors.edit.identifierHelpAdd')
                }
              >
                <Input
                  id={identifierInputId}
                  value={identifier}
                  readOnly
                  tabIndex={-1}
                  className="bg-muted/50 font-mono text-muted-foreground"
                  placeholder={t('connectors.edit.identifierPlaceholder')}
                  aria-invalid={liveIdentifierError ? true : undefined}
                  aria-describedby={describedBy(identifierInputId, liveIdentifierError, true)}
                  data-testid="connector-profile-name"
                />
              </FormField>
              <FormField id={descriptionInputId} label={t('common.description')}>
                <Textarea
                  id={descriptionInputId}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                  placeholder={t('connectors.edit.descriptionPlaceholder')}
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
                <Link to={listPath}>{t('common.cancel')}</Link>
              </Button>
              <Button
                type="submit"
                variant="pill-dark"
                size="pill"
                className="tracking-normal normal-case"
                disabled={saving}
                data-testid="connector-profile-save"
              >
                {saving
                  ? t('connectors.edit.saving')
                  : isEdit
                    ? t('connectors.edit.saveChanges')
                    : t('connectors.edit.saveProfile')}
              </Button>
            </div>
          </form>
        )}
      </Card>
      {leaveDialog}
    </main>
  );
}

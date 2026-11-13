import { X } from 'lucide-react';
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
      // Pattern comes from the server-side connector template, not end-user input.
      // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
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
function useUnsavedChangesGuard(dirty: boolean, saving: boolean, saved: { current: boolean }) {
  const { t } = useTranslation();
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      !saved.current && (dirty || saving) &&
      // Same page (self link or hash-only): nothing is left behind, so no prompt.
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );
  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (!saved.current && (dirty || saving)) {
          event.preventDefault();
          event.returnValue = '';
        }
      },
      [dirty, saving, saved],
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
      pending={saving}
      title={t('connectors.edit.unsaved.title')}
      description={t(saving ? 'connectors.edit.unsaved.saving' : 'connectors.edit.unsaved.description')}
      cancelLabel={t('connectors.edit.unsaved.keepEditing')}
      confirmLabel={t('connectors.edit.unsaved.discard')}
      onConfirm={() => blocker.proceed?.()}
    />
  );
}

type FieldStatus = 'configured' | 'notSet';

function ClearButton({ id, label, onClear }: { id: string; label: string; onClear: () => void }) {
  const { t } = useTranslation();
  const clearLabel = t('connectors.edit.actions.clear', { label });
  return (
    <button
      type="button"
      className="flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
      aria-label={clearLabel}
      title={clearLabel}
      onClick={() => {
        document.getElementById(id)?.focus();
        onClear();
      }}
    >
      <X className="size-4" aria-hidden />
    </button>
  );
}

function ClearableControl({ children, clearControl }: { children: ReactNode; clearControl?: ReactNode }) {
  return (
    <div className="relative">
      {children}
      {clearControl ? <div className="absolute right-0 top-0">{clearControl}</div> : null}
    </div>
  );
}

function FormField({
  id,
  label,
  required,
  status,
  staticLabel,
  help,
  error,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  status?: FieldStatus;
  staticLabel?: boolean;
  help?: ReactNode;
  error?: string | null;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const labelClassName = 'text-sm font-medium text-foreground';
  const labelContent = (
    <>
      {label}
      {required ? (
        <span className="ml-0.5 text-destructive" aria-hidden>
          *
        </span>
      ) : (
        <span className="ml-1 font-normal text-muted-foreground">{t('connectors.edit.optional')}</span>
      )}
    </>
  );
  return (
    <div className="mt-4 first:mt-0">
      <div className="flex items-center gap-2">
        {staticLabel ? (
          <span className={labelClassName}>{labelContent}</span>
        ) : (
          <label htmlFor={id} className={labelClassName}>{labelContent}</label>
        )}
        {status ? (
          <Badge
            variant={status === 'configured' ? 'success' : 'outline'}
            className="ml-auto"
            data-testid={`${id}-status`}
          >
            {t(`connectors.edit.status.${status}`)}
          </Badge>
        ) : null}
      </div>
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

function Section({ title, children, disabled }: { title: string; children: ReactNode; disabled?: boolean }) {
  return (
    <fieldset className="mt-7 first:mt-0" disabled={disabled}>
      <legend className="mb-3 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

export default function ConnectorProfileEditPage() {
  const { t } = useTranslation();
  const { connectorId, profileId } = useParams();
  return (
    <ConnectorsGate
      title={profileId ? t('connectors.editProfile') : t('connectors.addProfile')}
      requireTenant
    >
      <ConnectorProfileEditBody key={JSON.stringify([connectorId, profileId])} />
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
  const [removePrompt, setRemovePrompt] = useState<ConnectorFieldDescriptor | null>(null);
  const [saving, setSaving] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const saveInFlight = useRef(false);
  const saved = useRef(false);

  const fields = useMemo(() => template?.profileFields ?? [], [template]);
  const connectorName = template?.name ?? t('connectors.edit.connectorFallback');
  const title = isEdit
    ? t('connectors.edit.titleEdit', { name: connectorName })
    : t('connectors.edit.titleAdd', { name: connectorName });
  const identifier = isEdit ? (existing?.profile_name ?? '') : slugifyIdentifier(displayName);
  // Names saved before the rules existed keep working until changed.
  const keepsSavedName = isEdit && displayName.trim() === existing?.display_name;
  const legacyName = keepsSavedName && displayNameError(displayName) !== null;
  const config: Record<string, string> = {};
  let blankedRequiredField = false;
  for (const field of fields) {
    const value = (values[field.id] ?? '').trim();
    const previous = (existing?.config[field.id] ?? '').trim();
    if (value && value !== previous && !cleared.includes(field.id)) {
      config[field.id] = value;
    }
    // Blanking a required value is an invalid edit, even though it cannot produce a payload.
    if (!value && previous && field.required) {
      blankedRequiredField = true;
    }
  }
  const dirty = !loading && (isEdit
    ? existing !== null && (
        displayName.trim() !== existing.display_name.trim() ||
        description.trim() !== (existing.description ?? '').trim() ||
        cleared.length > 0 || blankedRequiredField || Object.keys(config).length > 0
      )
    : template !== null && Boolean(displayName || description || Object.keys(values).length));
  const leaveDialog = useUnsavedChangesGuard(dirty, saving, saved);

  useEffect(() => {
    if (!canWriteProfile) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTemplate(null);
    setExisting(null);
    setFieldErrors({});
    setRemovePrompt(null);
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
      const loadedValues: Record<string, string> = {};
      for (const field of loadedTemplate.profileFields) {
        const value = loadedProfile?.config[field.id];
        if (!isMasked(field) && value !== undefined) {
          loadedValues[field.id] = value;
        }
      }
      setTemplate(loadedTemplate);
      setExisting(loadedProfile && { ...loadedProfile, config: loadedValues });
      setTakenNames(new Set(siblings.map((profile) => profile.profile_name)));
      setDisplayName(loadedDisplayName);
      setDescription(loadedDescription);
      setValues(loadedValues);
      setCleared([]);
      setReplacing({});
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

  function hasStoredValue(field: ConnectorFieldDescriptor) {
    return Boolean(existing?.configured_secrets.includes(field.id) || existing?.config[field.id]?.trim());
  }

  function missingRequiredValue(field: ConnectorFieldDescriptor, value: string) {
    return field.required && !value.trim() && !(isMasked(field) && hasStoredValue(field));
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
      // Keep accepting unchanged legacy values, while flagging any missing required value.
      if (cleared.includes(field.id) || (value.trim() && !(field.id in config))) {
        continue;
      }
      const message = connectorFieldError(field, value, isMasked(field) && hasStoredValue(field));
      if (message) {
        next[field.id] = message;
      }
    }
    return next;
  }

  function setValue(fieldId: string, value: string) {
    setValues((prev) => ({ ...prev, [fieldId]: value }));
    setFieldErrors((prev) => withoutKeys(prev, fieldId));
    if (value.trim()) {
      setCleared((prev) => prev.includes(fieldId) ? prev.filter((id) => id !== fieldId) : prev);
    }
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
    setCleared((prev) => on ? [...prev, fieldId] : prev.filter((id) => id !== fieldId));
    if (on) {
      setValues((prev) => withoutKeys(prev, fieldId));
      setFieldErrors((prev) => withoutKeys(prev, fieldId));
      setReplacing((prev) => ({ ...prev, [fieldId]: false }));
    } else {
      resetValue(fieldId);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (saveInFlight.current || saved.current || !template || (isEdit && !dirty)) {
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
    saveInFlight.current = true;
    setSaving(true);
    setError(null);
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
      // The blocker can run before React commits another render.
      saved.current = true;
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
      saveInFlight.current = false;
      setSaving(false);
    }
  }

  const liveIdentifierError = fieldErrors.identifier ?? identifierError();
  const identifierInputId = 'connector-profile-input-identifier';
  const displayNameInputId = 'connector-profile-input-displayName';
  const descriptionInputId = 'connector-profile-input-description';
  const displayNameHelp = `3-60 characters. ${DISPLAY_NAME_HINT}`;
  const nameError = fieldErrors.displayName ??
    (isEdit && !displayName.trim() ? t('connectors.validation.displayNameRequired') : null);

  function focusNextFrame(id: string) {
    requestAnimationFrame(() => {
      const target = form.current?.ownerDocument.getElementById(id);
      if (target && form.current?.contains(target)) {
        target.focus();
      }
    });
  }

  function renderField(field: ConnectorFieldDescriptor) {
    const inputId = `connector-profile-input-${field.id}`;
    const stored = hasStoredValue(field);
    const isCleared = cleared.includes(field.id);
    const masked = isMasked(field);
    const savedCredential = masked && stored;
    const hideSecret = savedCredential && !replacing[field.id];
    const value = values[field.id] ?? '';
    const filled = Boolean(value.trim());
    const fieldError = fieldErrors[field.id] ?? (isEdit && missingRequiredValue(field, value)
      ? t('connectors.validation.required', { label: field.label })
      : null);
    const starttls = isEdit && connectorId === 'smtp' && field.id === 'smtp_starttls';
    const stripeMode = connectorId === 'stripe' && field.id === 'api_key' ? stripeKeyMode(value) : null;
    const keepsSavedSetting = !isCleared && !filled && !masked && field.type !== 'boolean' &&
      !field.required && Boolean(existing?.config[field.id]?.trim());
    const keepHint = keepsSavedSetting
      ? t('connectors.edit.keepSavedSetting')
      : savedCredential && !hideSecret && !filled ? t('connectors.edit.valueSaved') : null;
    const templateHelp = starttls ? t('connectors.edit.starttlsHelp') : field.helpText;
    const help = (
      <>
        {keepHint ? `${keepHint} ` : null}
        {templateHelp}
      </>
    );
    const hasHelp = Boolean(keepHint || templateHelp);
    const placeholder = field.example ? `e.g. ${field.example}` : undefined;
    const common = {
      id: inputId,
      'aria-invalid': fieldError ? true : undefined,
      'aria-required': field.required && !savedCredential ? true : undefined,
      'aria-describedby': [
        describedBy(inputId, fieldError, hasHelp ? help : null),
        isCleared ? `${inputId}-pending` : null,
      ].filter(Boolean).join(' ') || undefined,
      'data-testid': `connector-profile-field-${field.id}`,
    };
    const actionButton = (
      action: 'replace' | 'cancel' | 'remove' | 'undo',
      onClick: () => void,
    ) => (
      <Button
        id={`${inputId}-${action}`}
        type="button"
        variant="outline"
        size="sm"
        aria-label={t(`connectors.edit.actions.${action}`, { label: field.label.toLowerCase() })}
        onClick={onClick}
      >
        {t(`connectors.edit.actions.${action}Label`)}
      </Button>
    );
    const canClearSetting = !masked && stored && !field.required && !isCleared;
    const clearControl = isEdit && field.type !== 'boolean' && (value || canClearSetting) ? (
      <ClearButton
        id={inputId}
        label={field.label.toLowerCase()}
        onClear={() => canClearSetting ? setClear(field.id, true) : setValue(field.id, '')}
      />
    ) : undefined;

    let control: ReactNode;
    if (hideSecret) {
      control = isCleared ? null : (
        <div className="flex flex-wrap items-center gap-1.5">
          <div className="flex h-8 min-w-24 flex-1 items-center rounded-lg border border-input bg-muted/50 px-2.5 text-sm tracking-widest" aria-hidden>
            ••••••••
          </div>
          {actionButton('replace', () => setReplace(field.id, true))}
          {!field.required ? actionButton('remove', () => setRemovePrompt(field)) : null}
        </div>
      );
    } else if (field.type === 'boolean') {
      control = (
        <select
          {...common}
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          value={value}
          onChange={(event) => {
            if (!event.target.value && isEdit && stored && !field.required) {
              setClear(field.id, true);
            } else {
              setValue(field.id, event.target.value);
            }
          }}
        >
          <option value="">{t(starttls ? 'connectors.edit.notSetOff' : isEdit
            ? 'connectors.edit.status.notSet'
            : 'connectors.edit.offDefault')}</option>
          <option value="true">{t('connectors.edit.on')}</option>
          {isEdit ? <option value="false">{t('connectors.edit.off')}</option> : null}
        </select>
      );
    } else if (masked) {
      control = (
        <PasswordInput
          {...common}
          toggleLabel={field.label.toLowerCase()}
          clearControl={clearControl}
          value={value}
          onChange={(event) => setValue(field.id, event.target.value)}
          autoComplete="new-password"
          spellCheck={false}
          // Only mounts for a saved credential after Replace is pressed.
          autoFocus={savedCredential}
          placeholder={savedCredential ? t('connectors.edit.enterNewValue') : placeholder}
        />
      );
    } else {
      control = (
        <ClearableControl clearControl={clearControl}>
          <Input
            {...common}
            className={clearControl ? 'pr-9' : undefined}
            type={field.type === 'url' ? 'url' : field.type === 'email' ? 'email' : 'text'}
            inputMode={field.type === 'port' ? 'numeric' : undefined}
            value={value}
            onChange={(event) => setValue(field.id, event.target.value)}
            autoComplete="off"
            spellCheck={false}
            placeholder={placeholder}
          />
        </ClearableControl>
      );
    }

    return (
      <FormField
        key={field.id}
        id={inputId}
        label={field.label}
        required={field.required}
        staticLabel={hideSecret}
        status={isEdit && !isCleared
          ? (savedCredential ? 'configured' : !filled && !keepsSavedSetting ? 'notSet' : undefined)
          : undefined}
        error={fieldError}
        help={hasHelp ? help : null}
      >
        {control}
        {savedCredential && !hideSecret ? (
          <div className="mt-1.5">
            {actionButton('cancel', () => {
              setReplace(field.id, false);
              focusNextFrame(`${inputId}-replace`);
            })}
          </div>
        ) : null}
        {isCleared ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span id={`${inputId}-pending`} role="status">{t('connectors.edit.willClear')}</span>
            {actionButton('undo', () => {
              setClear(field.id, false);
              focusNextFrame(hideSecret ? `${inputId}-replace` : inputId);
            })}
          </div>
        ) : null}
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
        ) : template ? (
          <form ref={form} noValidate onSubmit={(event) => void handleSubmit(event)}>
            <p className="mb-5 text-[13px] text-muted-foreground">
              <Trans
                i18nKey="connectors.edit.requiredNote"
                components={{ req: <span className="text-destructive" /> }}
              />
            </p>
            <Section title={t('connectors.edit.detailsSection')} disabled={saving}>
              <FormField
                id={displayNameInputId}
                label={t('connectors.edit.displayName')}
                required
                status={isEdit && !displayName.trim() ? 'notSet' : undefined}
                error={nameError}
                help={displayNameHelp}
              >
                <ClearableControl clearControl={isEdit && displayName ? (
                  <ClearButton
                    id={displayNameInputId}
                    label={t('connectors.edit.displayName').toLocaleLowerCase()}
                    onClear={() => {
                      setDisplayName('');
                      setFieldErrors((prev) => withoutKeys(prev, 'displayName', 'identifier'));
                    }}
                  />
                ) : null}>
                  <Input
                    id={displayNameInputId}
                    className={isEdit && displayName ? 'pr-9' : undefined}
                    value={displayName}
                    onChange={(event) => {
                      setDisplayName(event.target.value);
                      setFieldErrors((prev) => withoutKeys(prev, 'displayName', 'identifier'));
                    }}
                    autoComplete="off"
                    placeholder={t('connectors.edit.displayNamePlaceholder', { name: connectorName })}
                    aria-invalid={nameError ? true : undefined}
                    aria-required
                    aria-describedby={describedBy(displayNameInputId, nameError, displayNameHelp)}
                    data-testid="connector-profile-display-name"
                  />
                </ClearableControl>
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
              <FormField
                id={descriptionInputId}
                label={t('common.description')}
                status={isEdit && !description.trim() ? 'notSet' : undefined}
              >
                <ClearableControl clearControl={isEdit && description ? (
                  <ClearButton
                    id={descriptionInputId}
                    label={t('common.description').toLocaleLowerCase()}
                    onClear={() => setDescription('')}
                  />
                ) : null}>
                  <Textarea
                    id={descriptionInputId}
                    className={isEdit && description ? 'pr-9' : undefined}
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    rows={3}
                    placeholder={t('connectors.edit.descriptionPlaceholder')}
                    data-testid="connector-profile-description"
                  />
                </ClearableControl>
              </FormField>
            </Section>

            {sections.map((section) => (
              <Section key={section.id} title={section.label} disabled={saving}>
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
                disabled={saving || (isEdit && !dirty)}
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
        ) : null}
      </Card>
      <ConfirmDialog
        open={removePrompt !== null}
        onOpenChange={(open) => {
          if (!open && removePrompt) {
            focusNextFrame(`connector-profile-input-${removePrompt.id}-remove`);
            setRemovePrompt(null);
          }
        }}
        pending={false}
        title={t('connectors.edit.removeSecret.title', { label: removePrompt?.label })}
        description={t('connectors.edit.removeSecret.description')}
        confirmLabel={t('common.remove')}
        onConfirm={() => {
          if (removePrompt) {
            setClear(removePrompt.id, true);
            focusNextFrame(`connector-profile-input-${removePrompt.id}-undo`);
            setRemovePrompt(null);
          }
        }}
      />
      {leaveDialog}
    </main>
  );
}

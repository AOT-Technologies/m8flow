import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { PasswordInput } from '@/components/ui/password-input';
import { Textarea } from '@/components/ui/textarea';
import { ApiError } from '@/lib/api';
import {
  createNamedValue,
  fetchNamedValue,
  namedValuesErrorMessage,
  updateNamedValue,
} from '@/lib/namedValuesApi';

import { ConfigurationBackButton } from './ConfigurationBackButton';
import { NamedValuesAccessDenied, NamedValuesGate, useNamedValuesContext } from './NamedValuesGate';

const NAME_PATTERN = /^[A-Za-z0-9_-]{1,255}$/;

export default function NamedValueEditPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const { canUpdateNamedValues } = useNamedValuesContext();
  const title = t(id
    ? canUpdateNamedValues ? 'configuration.namedValues.edit.title' : 'configuration.namedValues.view.title'
    : 'configuration.namedValues.new.title');
  const access = id ? 'item' : 'create';
  return (
    <NamedValuesGate title={title} access={access}>
      <NamedValueEditBody title={title} />
    </NamedValuesGate>
  );
}

function NamedValueEditBody({ title }: { title: string }) {
  const { t } = useTranslation();
  const { id } = useParams();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const {
    tenantId,
    isSuperAdmin,
    canReadNamedValueItems,
    canCreateNamedValues,
    canUpdateNamedValues,
  } = useNamedValuesContext();
  const allowed = isEdit
    ? canReadNamedValueItems && canUpdateNamedValues
    : canCreateNamedValues;
  const readOnly = isEdit && !canUpdateNamedValues;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [sensitive, setSensitive] = useState(false);
  const [initialSensitive, setInitialSensitive] = useState(false);
  const [value, setValue] = useState('');
  const [initialValue, setInitialValue] = useState('');
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [configured, setConfigured] = useState(false);

  useEffect(() => {
    if (!isEdit || !id || !canReadNamedValueItems) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setLoadError(null);
    setAccessDenied(false);
    fetchNamedValue(id, isSuperAdmin ? tenantId : null)
      .then((row) => {
        if (cancelled) return;
        setName(row.name);
        setDescription(row.description ?? '');
        setSensitive(row.isSensitive);
        setInitialSensitive(row.isSensitive);
        setConfigured(row.isConfigured);
        // The API deliberately omits sensitive values.
        const loadedValue = row.isSensitive ? '' : String(row.value ?? '');
        setValue(loadedValue);
        setInitialValue(loadedValue);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setAccessDenied(err instanceof ApiError && err.status === 403);
          setLoadError(namedValuesErrorMessage(err, t('configuration.namedValues.errors.load')));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canReadNamedValueItems, id, isEdit, isSuperAdmin, tenantId, t]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (saving || loading || loadError || !allowed) return;
    const cleanedName = name.trim();
    if (!NAME_PATTERN.test(cleanedName)) {
      setError(t('configuration.namedValues.validation.name'));
      return;
    }
    const cleanedValue = value;
    if ((!isEdit || sensitive !== initialSensitive) && !cleanedValue.trim()) {
      setError(t('configuration.namedValues.validation.valueRequired'));
      return;
    }
    setSaving(true);
    setError(null);
    const body = {
      name: cleanedName,
      description: description.trim() || null,
      is_sensitive: sensitive,
      ...(
        cleanedValue !== '' &&
        (!isEdit || cleanedValue !== initialValue || sensitive !== initialSensitive)
          ? { value: cleanedValue }
          : {}
      ),
    };
    try {
      if (isEdit && id) {
        await updateNamedValue(id, body, isSuperAdmin ? tenantId : null);
        navigate('/configuration/named-values');
      } else {
        await createNamedValue(body, isSuperAdmin ? tenantId : null);
        navigate('/configuration/named-values');
      }
      setValue('');
    } catch (err: unknown) {
      setError(namedValuesErrorMessage(err, t(isEdit ? 'configuration.namedValues.errors.update' : 'configuration.namedValues.errors.create')));
    } finally {
      setSaving(false);
    }
  }

  const listPath = '/configuration/named-values';
  if (accessDenied) {
    return <NamedValuesAccessDenied title={title} />;
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <ConfigurationBackButton label={t('configuration.namedValues.title')} to={listPath} />
        <h1 className="font-display text-[32px] font-semibold tracking-tight">
          {title}
        </h1>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          {t(isEdit
            ? readOnly ? 'configuration.namedValues.view.subtitle' : 'configuration.namedValues.edit.subtitle'
            : 'configuration.namedValues.new.subtitle')}
        </p>
      </div>
      {error ? <Alert tone="error" className="mb-4 max-w-lg" role="alert">{error}</Alert> : null}
      {loadError ? <Alert tone="error" className="mb-4 max-w-lg" role="alert">{loadError}</Alert> : (
      <Card variant="bordered" className="max-w-lg p-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">{t('configuration.namedValues.loading')}</p>
        ) : readOnly ? (
          <dl className="space-y-4 text-sm">
            <div>
              <dt className="font-medium">{t('configuration.namedValues.name')}</dt>
              <dd className="mt-1 break-words">{name}</dd>
            </div>
            <div>
              <dt className="font-medium">{t('common.description')}</dt>
              <dd className="mt-1 whitespace-pre-wrap break-words">{description || t('common.none')}</dd>
            </div>
            <div>
              <dt className="font-medium">{t('configuration.namedValues.columns.sensitivity')}</dt>
              <dd className="mt-1">{t(sensitive ? 'configuration.namedValues.sensitive' : 'configuration.namedValues.standard')}</dd>
            </div>
            <div>
              <dt className="font-medium">{t('common.status')}</dt>
              <dd className="mt-1">{t(configured ? 'configuration.namedValues.configured' : 'configuration.namedValues.notConfigured')}</dd>
            </div>
            <div>
              <dt className="font-medium">{t('configuration.namedValues.value')}</dt>
              <dd className="mt-1 whitespace-pre-wrap break-words">{sensitive ? t('configuration.namedValues.sensitiveHelp') : value}</dd>
            </div>
          </dl>
        ) : (
          <form onSubmit={(event) => void handleSubmit(event)}>
            <label className="block text-sm font-medium text-foreground" htmlFor="named-value-name">
              {t('configuration.namedValues.name')}
            </label>
            <Input
              id="named-value-name"
              className="mt-1.5"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="off"
              required
              data-testid="named-value-name"
            />
            <label className="mt-4 block text-sm font-medium text-foreground" htmlFor="named-value-description">
              {t('common.description')}
            </label>
            <Textarea
              id="named-value-description"
              className="mt-1.5"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              data-testid="named-value-description"
            />
            <label className="mt-4 flex items-center gap-2 text-sm font-medium text-foreground">
              <input
                type="checkbox"
                checked={sensitive}
                onChange={(event) => setSensitive(event.target.checked)}
                data-testid="named-value-sensitive"
              />
              {t('configuration.namedValues.sensitive')}
            </label>
            <p className="mt-1 text-[13px] text-muted-foreground">
              {sensitive
                ? t('configuration.namedValues.sensitiveHelp')
                : t('configuration.namedValues.standardHelp')}
            </p>
            <label className="mt-4 block text-sm font-medium text-foreground" htmlFor="named-value-value">
              {t('configuration.namedValues.value')}
            </label>
            {sensitive ? (
              <PasswordInput
                id="named-value-value"
                className="mt-1.5"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                autoComplete="new-password"
                toggleLabel={t('configuration.namedValues.value').toLowerCase()}
                placeholder={isEdit ? t('configuration.namedValues.valueKeep') : undefined}
                data-testid="named-value-value"
              />
            ) : (
              <Input
                id="named-value-value"
                className="mt-1.5"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                autoComplete="off"
                data-testid="named-value-value"
              />
            )}
            {isEdit && initialSensitive && sensitive ? (
              <p className="mt-1 text-[13px] text-muted-foreground">{t('configuration.namedValues.valueKeep')}</p>
            ) : null}
            <div className="mt-6 flex flex-wrap gap-2">
              <Button asChild type="button" variant="pill-cancel" size="pill">
                <Link to={listPath}>{t('common.cancel')}</Link>
              </Button>
              <Button
                type="submit"
                variant="pill-dark"
                size="pill"
                disabled={saving || loading}
                data-testid="named-value-save"
              >
                {saving ? t('configuration.saving') : t(isEdit ? 'configuration.namedValues.edit.save' : 'configuration.namedValues.new.save')}
              </Button>
            </div>
          </form>
        )}
      </Card>)}
    </main>
  );
}

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  PROFILE_NAME_RE,
  connectorsErrorMessage,
  createConnectorProfile,
  fetchConnectorProfile,
  fetchConnectorTemplate,
  updateConnectorProfile,
  type ConnectorFieldDescriptor,
  type ConnectorProfile,
  type ConnectorTemplate,
} from '@/lib/connectorsApi';

import { ConnectorsGate, useConnectorsContext } from './ConnectorsGate';

export default function ConnectorProfileEditPage() {
  const { profileId } = useParams();
  const title = profileId ? 'Edit profile' : 'Add profile';
  return (
    <ConnectorsGate title={title} requireTenant>
      <ConnectorProfileEditBody />
    </ConnectorsGate>
  );
}

function ConnectorProfileEditBody() {
  const { connectorId = '', profileId } = useParams();
  const isEdit = Boolean(profileId);
  const title = isEdit ? 'Edit profile' : 'Add profile';
  const navigate = useNavigate();
  const { scopedTenantId, canManageConnectorProfiles } = useConnectorsContext();
  const listPath = `/connectors/${encodeURIComponent(connectorId)}/profiles`;

  const [template, setTemplate] = useState<ConnectorTemplate | null>(null);
  const [existing, setExisting] = useState<ConnectorProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [profileName, setProfileName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!canManageConnectorProfiles) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const load = async () => {
      const loadedTemplate = await fetchConnectorTemplate(connectorId);
      let loadedProfile: ConnectorProfile | null = null;
      if (isEdit && profileId) {
        loadedProfile = await fetchConnectorProfile(Number(profileId), scopedTenantId);
      }
      if (cancelled) {
        return;
      }
      setTemplate(loadedTemplate);
      setExisting(loadedProfile);
      if (loadedProfile) {
        setProfileName(loadedProfile.profile_name);
        setDisplayName(loadedProfile.display_name);
        setDescription(loadedProfile.description ?? '');
        setValues({ ...loadedProfile.config });
      }
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

  const fields = template?.profileFields ?? [];
  const grouped = useMemo(() => {
    const groups = template?.groups?.length ? template.groups : [{ id: '', label: '' }];
    return groups
      .map((group) => ({
        group,
        fields: fields.filter((field) => field.group === group.id || !group.id),
      }))
      .filter((entry) => entry.fields.length > 0);
  }, [template, fields]);

  function isConfigured(field: ConnectorFieldDescriptor) {
    return Boolean(existing?.configured_secrets.includes(field.id));
  }

  if (!canManageConnectorProfiles) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
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

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const cleanedName = profileName.trim();
    if (!isEdit && !PROFILE_NAME_RE.test(cleanedName)) {
      setError(
        'Use 1-64 letters, digits, ".", "-" or "_", starting and ending with a letter or digit.',
      );
      return;
    }
    if (saving) {
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
          {
            display_name: displayName.trim() || profileName,
            description: description.trim() || null,
            config,
          },
          scopedTenantId,
        );
      } else {
        await createConnectorProfile(
          {
            connector_type: connectorId,
            profile_name: cleanedName,
            display_name: displayName.trim() || cleanedName,
            description: description.trim() || null,
            config,
          },
          scopedTenantId,
        );
      }
      navigate(listPath);
    } catch (err: unknown) {
      setError(connectorsErrorMessage(err, 'Could not save the profile.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <p className="mb-2 text-sm text-muted-foreground">
          <Link to="/connectors" className="hover:underline">
            Connectors
          </Link>
          {' / '}
          <Link to={listPath} className="hover:underline">
            {template?.name ?? connectorId}
          </Link>
        </p>
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 max-w-xl text-sm text-muted-foreground">
          Stored secret values are never shown. Leave a secret blank on edit to keep it.
        </p>
      </div>

      {error ? <Alert tone="error" className="mb-4">{error}</Alert> : null}

      <Card variant="bordered" className="max-w-lg p-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading profile…</p>
        ) : (
          <form onSubmit={(event) => void handleSubmit(event)}>
            <label className="block text-sm font-medium text-foreground">
              Identifier
              <Input
                className="mt-1.5"
                value={profileName}
                onChange={(event) => setProfileName(event.target.value)}
                disabled={isEdit}
                autoComplete="off"
                required={!isEdit}
                data-testid="connector-profile-name"
              />
            </label>
            <p className="mt-1.5 text-[13px] text-muted-foreground">
              The name Service Tasks select, for example http-prod. Cannot be changed later.
            </p>
            <label className="mt-4 block text-sm font-medium text-foreground">
              Display name
              <Input
                className="mt-1.5"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                autoComplete="off"
                data-testid="connector-profile-display-name"
              />
            </label>
            <label className="mt-4 block text-sm font-medium text-foreground">
              Description
              <Textarea
                className="mt-1.5"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
                data-testid="connector-profile-description"
              />
            </label>
            {grouped.map(({ group, fields: groupFields }) => (
              <fieldset key={group.id || 'default'} className="mt-6">
                {group.label ? (
                  <legend className="mb-3 text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
                    {group.label}
                  </legend>
                ) : null}
                {groupFields.map((field) => {
                  const configured = isConfigured(field);
                  const isSecret = Boolean(field.secret) || field.type === 'password';
                  const shown = Boolean(visible[field.id]);
                  return (
                    <label key={field.id} className="mt-3 block text-sm font-medium text-foreground">
                      {field.label}
                      <Input
                        className="mt-1.5"
                        type={isSecret && !shown ? 'password' : 'text'}
                        value={values[field.id] ?? ''}
                        onChange={(event) =>
                          setValues((prev) => ({ ...prev, [field.id]: event.target.value }))
                        }
                        autoComplete={isSecret ? 'new-password' : 'off'}
                        placeholder={configured ? 'Configured. Leave blank to keep.' : field.example}
                        data-testid={`connector-profile-field-${field.id}`}
                      />
                      {isSecret ? (
                        <button
                          type="button"
                          className="mt-1.5 text-[13px] text-muted-foreground hover:underline"
                          onClick={() =>
                            setVisible((prev) => ({ ...prev, [field.id]: !prev[field.id] }))
                          }
                        >
                          {shown ? 'Hide' : 'Show'}
                        </button>
                      ) : null}
                    </label>
                  );
                })}
              </fieldset>
            ))}
            <div className="mt-6 flex flex-wrap gap-2">
              <Button asChild type="button" variant="pill-cancel" size="pill">
                <Link to={listPath}>Cancel</Link>
              </Button>
              <Button
                type="submit"
                variant="pill-dark"
                size="pill"
                disabled={saving || (!isEdit && !profileName.trim())}
                data-testid="connector-profile-save"
              >
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        )}
      </Card>
    </main>
  );
}

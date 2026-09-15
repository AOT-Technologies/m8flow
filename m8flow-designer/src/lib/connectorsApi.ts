import { apiFetch, apiGet, ApiError } from './api';

export type ConnectorFieldDescriptor = {
  id: string;
  label: string;
  type: string;
  required: boolean;
  secret?: boolean;
  group?: string;
  helpText?: string;
  example?: string;
};

export type ConnectorTemplate = {
  id: string;
  name: string;
  description: string;
  supportsProfiles?: boolean;
  groups?: { id: string; label: string }[];
  profileFields: ConnectorFieldDescriptor[];
};

export type ConnectorProfile = {
  id: number;
  connector_type: string;
  profile_name: string;
  display_name: string;
  description: string | null;
  config: Record<string, string>;
  configured_secrets: string[];
  is_active: boolean;
};

export type ConnectorProfilePayload = {
  connector_type?: string;
  profile_name?: string;
  display_name?: string;
  description?: string | null;
  config?: Record<string, string>;
  is_active?: boolean;
};

export type ConnectorProfileListFilters = {
  connectorType?: string;
  includeInactive?: boolean;
  tenantId?: string | null;
};

export const PROFILE_NAME_RE =
  /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$/;

function tenantParams(tenantId?: string | null): URLSearchParams {
  const params = new URLSearchParams();
  if (tenantId) {
    params.set('tenantId', tenantId);
  }
  return params;
}

function withQuery(path: string, params: URLSearchParams): string {
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

function asProfile(value: unknown): ConnectorProfile | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const id = Number(record.id);
  const connectorType = typeof record.connector_type === 'string' ? record.connector_type : '';
  const profileName = typeof record.profile_name === 'string' ? record.profile_name : '';
  if (!Number.isFinite(id) || !connectorType || !profileName) {
    return null;
  }
  const config: Record<string, string> = {};
  if (record.config && typeof record.config === 'object' && !Array.isArray(record.config)) {
    for (const [key, raw] of Object.entries(record.config as Record<string, unknown>)) {
      if (raw === null || raw === undefined) {
        continue;
      }
      config[key] = String(raw);
    }
  }
  const configured = Array.isArray(record.configured_secrets)
    ? record.configured_secrets.filter((name): name is string => typeof name === 'string')
    : [];
  return {
    id,
    connector_type: connectorType,
    profile_name: profileName,
    display_name:
      typeof record.display_name === 'string' && record.display_name.trim()
        ? record.display_name
        : profileName,
    description: typeof record.description === 'string' ? record.description : null,
    config,
    configured_secrets: configured,
    is_active: record.is_active !== false,
  };
}

export function connectorsErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'serverMessage' in error) {
    const serverMessage = (error as { serverMessage?: unknown }).serverMessage;
    if (typeof serverMessage === 'string' && serverMessage.trim()) {
      return serverMessage;
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function connectorTemplatePath(connectorType: string): string {
  return `/v1.0/m8flow/connector-templates/${encodeURIComponent(connectorType)}`;
}

export function connectorProfilesPath(filters: ConnectorProfileListFilters = {}): string {
  const params = tenantParams(filters.tenantId);
  if (filters.connectorType) {
    params.set('connector_type', filters.connectorType);
  }
  if (filters.includeInactive === false) {
    params.set('include_inactive', 'false');
  }
  return withQuery('/v1.0/m8flow/connector-profiles', params);
}

export function connectorProfileItemPath(
  profileId: number,
  tenantId?: string | null,
  extra?: Record<string, string>,
): string {
  const params = tenantParams(tenantId);
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      params.set(key, value);
    }
  }
  return withQuery(`/v1.0/m8flow/connector-profiles/${profileId}`, params);
}

export async function fetchConnectorTemplate(connectorType: string): Promise<ConnectorTemplate> {
  const body = await apiGet<unknown>(connectorTemplatePath(connectorType));
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new ApiError(connectorTemplatePath(connectorType), 200, 'GET', 'Template was unreadable.');
  }
  const record = body as Record<string, unknown>;
  const fields = Array.isArray(record.profileFields) ? record.profileFields : [];
  return {
    id: typeof record.id === 'string' ? record.id : connectorType,
    name: typeof record.name === 'string' ? record.name : connectorType,
    description: typeof record.description === 'string' ? record.description : '',
    supportsProfiles: record.supportsProfiles === true,
    groups: Array.isArray(record.groups)
      ? (record.groups as ConnectorTemplate['groups'])
      : [],
    profileFields: fields.filter(
      (field): field is ConnectorFieldDescriptor =>
        !!field && typeof field === 'object' && typeof (field as { id?: unknown }).id === 'string',
    ),
  };
}

export async function fetchConnectorProfiles(
  filters: ConnectorProfileListFilters = {},
): Promise<ConnectorProfile[]> {
  const body = await apiGet<unknown>(connectorProfilesPath(filters));
  if (!Array.isArray(body)) {
    return [];
  }
  return body.flatMap((row) => {
    const profile = asProfile(row);
    return profile ? [profile] : [];
  });
}

export async function fetchConnectorProfile(
  profileId: number,
  tenantId?: string | null,
): Promise<ConnectorProfile> {
  const path = connectorProfileItemPath(profileId, tenantId);
  const profile = asProfile(await apiGet<unknown>(path));
  if (!profile) {
    throw new ApiError(path, 200, 'GET', 'Profile metadata was unreadable.');
  }
  return profile;
}

export async function createConnectorProfile(
  payload: ConnectorProfilePayload,
  tenantId?: string | null,
): Promise<ConnectorProfile> {
  const path = connectorProfilesPath({ tenantId });
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  const profile = asProfile(await response.json());
  if (!profile) {
    throw new ApiError(path, 201, 'POST', 'Profile metadata was unreadable.');
  }
  return profile;
}

export async function updateConnectorProfile(
  profileId: number,
  payload: ConnectorProfilePayload,
  tenantId?: string | null,
): Promise<ConnectorProfile> {
  const path = connectorProfileItemPath(profileId, tenantId);
  const response = await apiFetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  const profile = asProfile(await response.json());
  if (!profile) {
    throw new ApiError(path, 200, 'PUT', 'Profile metadata was unreadable.');
  }
  return profile;
}

export async function deactivateConnectorProfile(
  profileId: number,
  tenantId?: string | null,
): Promise<void> {
  await apiFetch(connectorProfileItemPath(profileId, tenantId), { method: 'DELETE' });
}

export async function deleteConnectorProfile(
  profileId: number,
  tenantId?: string | null,
): Promise<void> {
  await apiFetch(connectorProfileItemPath(profileId, tenantId, { hard: 'true' }), {
    method: 'DELETE',
  });
}

export type ConnectorProfilePickerOption = {
  profile_name: string;
  display_name: string;
};

export type ConnectorProfilePickerPayload = {
  profiles: ConnectorProfilePickerOption[];
  hiddenFieldIds: string[];
  supportsProfiles: boolean;
};

/** Active profiles for the modeler Config tab. Always `include_inactive=false`. */
export async function fetchConnectorProfilesForPicker(
  connectorType: string,
  tenantId?: string | null,
): Promise<ConnectorProfilePickerPayload> {
  const [template, profiles] = await Promise.all([
    fetchConnectorTemplate(connectorType).catch(() => null),
    fetchConnectorProfiles({
      connectorType,
      includeInactive: false,
      tenantId,
    }).catch(() => [] as ConnectorProfile[]),
  ]);
  if (!template?.supportsProfiles) {
    return { profiles: [], hiddenFieldIds: [], supportsProfiles: false };
  }
  return {
    profiles: profiles
      .filter((profile) => profile.is_active)
      .map((profile) => ({
        profile_name: profile.profile_name,
        display_name: profile.display_name,
      })),
    hiddenFieldIds: template.profileFields.map((field) => field.id),
    supportsProfiles: true,
  };
}


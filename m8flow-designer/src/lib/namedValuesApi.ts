import i18n from '@/i18n';

import { apiFetch, apiGet, ApiError } from './api';

export type NamedValue = {
  id: string;
  tenantId: string;
  name: string;
  description: string | null;
  isSensitive: boolean;
  isConfigured: boolean;
  /** Null for sensitive entries. Sensitive values are always write-only. */
  value: string | number | boolean | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type NamedValueInput = {
  name: string;
  description?: string | null;
  is_sensitive?: boolean;
  value?: string | number | boolean;
};

const COLLECTION_PATH = '/v1.0/m8flow/named-values';

function tenantQuery(tenantId?: string | null): string {
  return tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
}

export function namedValuesPath(tenantId?: string | null): string {
  return `${COLLECTION_PATH}${tenantQuery(tenantId)}`;
}

export function namedValueItemPath(id: string, tenantId?: string | null): string {
  return `${COLLECTION_PATH}/${encodeURIComponent(id)}${tenantQuery(tenantId)}`;
}

export function namedValuesErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'serverMessage' in error) {
    const message = (error as { serverMessage?: unknown }).serverMessage;
    if (typeof message === 'string' && message.trim()) return message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function parseNamedValue(raw: unknown, path: string): NamedValue {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new ApiError(path, 200, 'GET', i18n.t('configuration.namedValues.errors.unreadable'));
  }
  const value = raw as Record<string, unknown>;
  return {
    id: String(value.id ?? ''),
    tenantId: String(value.tenantId ?? ''),
    name: String(value.name ?? ''),
    description: typeof value.description === 'string' ? value.description : null,
    isSensitive: value.isSensitive === true,
    isConfigured: value.isConfigured === true,
    value: value.isSensitive === true ? null : (value.value as NamedValue['value']) ?? null,
    createdAt: typeof value.createdAt === 'string' ? value.createdAt : null,
    updatedAt: typeof value.updatedAt === 'string' ? value.updatedAt : null,
  };
}

export async function fetchNamedValues(tenantId?: string | null): Promise<NamedValue[]> {
  const path = namedValuesPath(tenantId);
  const response = await apiGet<unknown>(path);
  if (!Array.isArray(response)) return [];
  return response.map((row) => parseNamedValue(row, path));
}

export async function fetchNamedValue(id: string, tenantId?: string | null): Promise<NamedValue> {
  const path = namedValueItemPath(id, tenantId);
  return parseNamedValue(await apiGet<unknown>(path), path);
}

export async function createNamedValue(
  input: NamedValueInput,
  tenantId?: string | null,
): Promise<NamedValue> {
  const path = namedValuesPath(tenantId);
  const response = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(input),
  });
  return parseNamedValue(await response.json(), path);
}

export async function updateNamedValue(
  id: string,
  input: Partial<NamedValueInput>,
  tenantId?: string | null,
): Promise<NamedValue> {
  const path = namedValueItemPath(id, tenantId);
  const response = await apiFetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(input),
  });
  return parseNamedValue(await response.json(), path);
}

export async function deleteNamedValue(id: string, tenantId?: string | null): Promise<void> {
  await apiFetch(namedValueItemPath(id, tenantId), { method: 'DELETE' });
}

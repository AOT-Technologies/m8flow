import { apiFetch, apiGet, ApiError } from './api';

export type Secret = {
  id: string | number;
  key: string;
  user_id: number;
  created_at_in_seconds: number | null;
  updated_at_in_seconds: number | null;
  username?: string | null;
  tenantId?: string;
  tenantName?: string | null;
};

export type SecretPagination = {
  count: number;
  total: number;
  pages: number;
};

export type SecretListResponse = {
  results: Secret[];
  pagination: SecretPagination;
};

export type SecretListFilters = {
  page?: number;
  perPage?: number;
  /** Super-admin only; `tenantId` query for cross-tenant list. */
  tenantId?: string | null;
};

const EMPTY_LIST: SecretListResponse = {
  results: [],
  pagination: { count: 0, total: 0, pages: 0 },
};

function omitValue(row: unknown): Secret | null {
  if (!row || typeof row !== 'object' || Array.isArray(row)) {
    return null;
  }
  const copy = { ...(row as Record<string, unknown>) };
  delete copy.value;
  return copy as Secret;
}

function secretsQuery(filters: SecretListFilters = {}): string {
  const params = new URLSearchParams();
  if (filters.page !== undefined) {
    params.set('page', String(filters.page));
  }
  if (filters.perPage !== undefined) {
    params.set('per_page', String(filters.perPage));
  }
  if (filters.tenantId) {
    params.set('tenantId', filters.tenantId);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

function tenantQuery(tenantId: string | null | undefined): string {
  if (!tenantId) {
    return '';
  }
  return `?tenantId=${encodeURIComponent(tenantId)}`;
}

export function secretsListPath(filters: SecretListFilters = {}): string {
  return `/v1.0/secrets${secretsQuery(filters)}`;
}

export function secretItemPath(key: string, tenantId?: string | null): string {
  return `/v1.0/secrets/${encodeURIComponent(key)}${tenantQuery(tenantId)}`;
}

export function secretsErrorMessage(error: unknown, fallback: string): string {
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

export async function fetchSecrets(
  filters: SecretListFilters = {},
): Promise<SecretListResponse> {
  const body = await apiGet<unknown>(secretsListPath(filters));
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return EMPTY_LIST;
  }
  const record = body as { results?: unknown; pagination?: SecretPagination };
  const results = Array.isArray(record.results)
    ? record.results.flatMap((row) => {
        const secret = omitValue(row);
        return secret ? [secret] : [];
      })
    : [];
  const pagination = record.pagination ?? EMPTY_LIST.pagination;
  return { results, pagination };
}

export async function fetchSecret(key: string, tenantId?: string | null): Promise<Secret> {
  const body = await apiGet<unknown>(secretItemPath(key, tenantId));
  const secret = omitValue(body);
  if (!secret) {
    throw new ApiError(secretItemPath(key, tenantId), 200, 'GET', 'Secret metadata was unreadable.');
  }
  return secret;
}

export async function createSecret(
  key: string,
  value: string,
  tenantId?: string | null,
): Promise<Secret> {
  const response = await apiFetch(`/v1.0/secrets${tenantQuery(tenantId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ key, value }),
  });
  const secret = omitValue(await response.json());
  if (!secret) {
    throw new ApiError(
      `/v1.0/secrets${tenantQuery(tenantId)}`,
      201,
      'POST',
      'Secret metadata was unreadable.',
    );
  }
  return secret;
}

export async function updateSecret(
  key: string,
  value: string,
  tenantId?: string | null,
): Promise<void> {
  await apiFetch(secretItemPath(key, tenantId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ value }),
  });
}

export async function deleteSecret(key: string, tenantId?: string | null): Promise<void> {
  await apiFetch(secretItemPath(key, tenantId), { method: 'DELETE' });
}

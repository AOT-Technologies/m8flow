import { apiFetch, apiGet, apiPost } from './api';

// Same `serverMessage`-first rule as every other *Api module.
export { secretsErrorMessage as natsTokensErrorMessage } from './secretsApi';

/** Key metadata. The backend never returns the key value here. */
export type NatsApiKey = {
  id: string;
  label: string;
  scope?: string | null;
  expiresAtInSeconds?: number | null;
  lastUsedAtInSeconds?: number | null;
  revokedAtInSeconds?: number | null;
  createdAtInSeconds?: number | null;
  createdBy?: string | null;
};

/** `null` = never expires. Must match the backend's ALLOWED_EXPIRY_DAYS. */
export type NatsApiKeyExpiryDays = 30 | 90 | 365 | null;

export type NatsApiKeyCreateInput = {
  label: string;
  expiresInDays: NatsApiKeyExpiryDays;
  /** Allowed process identifiers; omit for any process in the tenant. */
  scope?: string[];
};

/** The one response that carries the raw key — it can never be fetched again. */
export type CreatedNatsApiKey = NatsApiKey & { token: string };

const BASE = '/v1.0/m8flow/nats-tokens';

/** Super-admins pick the tenant via `tenantId`; everyone else is cookie-scoped. */
function tenantQuery(tenantId: string | null | undefined): string {
  return tenantId ? `?tenantId=${encodeURIComponent(tenantId)}` : '';
}

export async function fetchNatsApiKeys(tenantId?: string | null): Promise<NatsApiKey[]> {
  const body = await apiGet<{ keys?: unknown }>(`${BASE}${tenantQuery(tenantId)}`);
  return Array.isArray(body?.keys) ? (body.keys as NatsApiKey[]) : [];
}

export function createNatsApiKey(
  input: NatsApiKeyCreateInput,
  tenantId?: string | null,
): Promise<CreatedNatsApiKey> {
  return apiPost<CreatedNatsApiKey>(`${BASE}${tenantQuery(tenantId)}`, input);
}

export async function revokeNatsApiKey(keyId: string, tenantId?: string | null): Promise<void> {
  await apiFetch(`${BASE}/${encodeURIComponent(keyId)}${tenantQuery(tenantId)}`, {
    method: 'DELETE',
  });
}

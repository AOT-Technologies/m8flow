import { apiFetch, apiGet, ApiError } from './api';

export const MAX_TENANT_NAME_LENGTH = 50;
const GENERATED_ALIAS_FALLBACK = 'tenant';

export type TenantStatus = 'ACTIVE' | 'INACTIVE' | 'DELETED';

export type Tenant = {
  id: string;
  name: string;
  slug: string;
  status: TenantStatus;
};

const STATUSES = new Set<TenantStatus>(['ACTIVE', 'INACTIVE', 'DELETED']);

export function tenantsErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.serverMessage) {
    return error.serverMessage;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function validateTenantDisplayName(value: string): string | null {
  if (!value) {
    return 'Tenant name cannot be empty.';
  }
  if (value.length > MAX_TENANT_NAME_LENGTH) {
    return `Tenant name must be ${MAX_TENANT_NAME_LENGTH} characters or fewer.`;
  }
  return null;
}

export function isDuplicateTenantName(
  name: string,
  existingTenants: Tenant[],
  excludeTenantId?: string,
): boolean {
  const normalized = name.trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return existingTenants.some(
    (tenant) =>
      tenant.id !== excludeTenantId && tenant.name.trim().toLowerCase() === normalized,
  );
}

export function generateTenantAliasBase(name: string): string {
  const sanitized = name
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-');
  return sanitized || GENERATED_ALIAS_FALLBACK;
}

export function generateUniqueTenantAlias(name: string, existingTenants: Tenant[]): string {
  const base = generateTenantAliasBase(name);
  const taken = new Set(
    existingTenants
      .map((tenant) => tenant.slug.trim().toLowerCase())
      .filter(Boolean),
  );
  if (!taken.has(base)) {
    return base;
  }
  let suffix = 2;
  while (taken.has(`${base}-${suffix}`)) {
    suffix += 1;
  }
  return `${base}-${suffix}`;
}

function asStatus(value: unknown): TenantStatus {
  return typeof value === 'string' && STATUSES.has(value as TenantStatus)
    ? (value as TenantStatus)
    : 'ACTIVE';
}

function asTenant(value: unknown): Tenant | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const id = typeof record.id === 'string' ? record.id.trim() : '';
  if (!id) {
    return null;
  }
  const name = typeof record.name === 'string' && record.name.trim() ? record.name.trim() : id;
  const slug =
    typeof record.slug === 'string' && record.slug.trim()
      ? record.slug.trim()
      : typeof record.alias === 'string' && record.alias.trim()
        ? record.alias.trim()
        : id;
  return { id, name, slug, status: asStatus(record.status) };
}

export async function fetchTenants(): Promise<Tenant[]> {
  const rows = await apiGet<unknown>('/v1.0/m8flow/tenants');
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows.flatMap((row) => {
    const tenant = asTenant(row);
    return tenant ? [tenant] : [];
  });
}

export async function createTenant(name: string, existingTenants: Tenant[]): Promise<Tenant> {
  const trimmed = name.trim();
  const slug = generateUniqueTenantAlias(trimmed, existingTenants);
  const response = await apiFetch('/v1.0/m8flow/tenant-realms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ slug, name: trimmed }),
  });
  const body: unknown = await response.json();
  const created = asTenant(body);
  if (created) {
    return created;
  }
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const id = typeof record.id === 'string' ? record.id : '';
  const alias = typeof record.alias === 'string' ? record.alias : slug;
  const display =
    typeof record.name === 'string'
      ? record.name
      : typeof record.displayName === 'string'
        ? record.displayName
        : trimmed;
  return {
    id: id || alias,
    name: display || trimmed,
    slug: alias || slug,
    status: 'ACTIVE',
  };
}

export async function updateTenantName(tenantId: string, name: string): Promise<void> {
  await apiFetch(`/v1.0/m8flow/tenants/${encodeURIComponent(tenantId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ name: name.trim() }),
  });
}

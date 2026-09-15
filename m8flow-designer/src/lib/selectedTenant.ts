/**
 * Super-admin sidebar tenant filter. Same key as m8flow-frontend
 * GlobalTenantContext — a UI filter, not tenant finalization.
 * Empty / missing means All Tenants. Backend truth stays the
 * `m8flow_selected_tenant` cookie (regular users / TenantSelectPage).
 */
export const GLOBAL_TENANT_STORAGE_KEY = 'm8flow_global_selected_tenant';

function safeGet(key: string): string {
  if (typeof window === 'undefined') {
    return '';
  }
  try {
    return window.localStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function safeSet(key: string, value: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

function safeRemove(key: string): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export function readPersistedTenantId(): string | null {
  const value = safeGet(GLOBAL_TENANT_STORAGE_KEY).trim();
  return value ? value : null;
}

export function persistTenantId(tenantId: string | null): void {
  if (tenantId) {
    safeSet(GLOBAL_TENANT_STORAGE_KEY, tenantId);
  } else {
    safeRemove(GLOBAL_TENANT_STORAGE_KEY);
  }
}

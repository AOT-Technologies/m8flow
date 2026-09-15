import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  GLOBAL_TENANT_STORAGE_KEY,
  persistTenantId,
  readPersistedTenantId,
} from './selectedTenant';

afterEach(() => {
  vi.restoreAllMocks();
  try {
    localStorage.clear();
  } catch {
    /* ignore */
  }
});

describe('selectedTenant persistence', () => {
  it('reads a stored tenant id', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'tenant-42');
    expect(readPersistedTenantId()).toBe('tenant-42');
  });

  it('treats missing or blank as All Tenants (null)', () => {
    expect(readPersistedTenantId()).toBeNull();
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, '   ');
    expect(readPersistedTenantId()).toBeNull();
  });

  it('persists a concrete tenant and clears All Tenants', () => {
    persistTenantId('tenant-7');
    expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBe('tenant-7');
    persistTenantId(null);
    expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBeNull();
  });

  it('does not throw when localStorage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });

    expect(readPersistedTenantId()).toBeNull();
    expect(() => persistTenantId('tenant-9')).not.toThrow();
    expect(() => persistTenantId(null)).not.toThrow();
  });
});

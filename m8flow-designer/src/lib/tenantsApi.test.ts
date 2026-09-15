import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  generateTenantAliasBase,
  generateUniqueTenantAlias,
  isDuplicateTenantName,
  validateTenantDisplayName,
  type Tenant,
} from './tenantsApi';

const { getAccessToken, resumeLoginAfterLogout } = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  resumeLoginAfterLogout: vi.fn(),
}));

vi.mock('./auth', () => ({
  getAccessToken,
  resumeLoginAfterLogout,
}));

const ACME: Tenant = { id: 't1', name: 'Acme Corp', slug: 'acme-corp', status: 'ACTIVE' };
const BETA: Tenant = { id: 't2', name: 'Beta', slug: 'beta', status: 'INACTIVE' };

const makeResponse = ({
  ok,
  status,
  body,
}: {
  ok: boolean;
  status: number;
  body?: unknown;
}) => ({
  ok,
  status,
  statusText: ok ? 'OK' : 'Error',
  json: vi.fn().mockResolvedValue(body ?? {}),
  clone: vi.fn().mockReturnThis(),
  text: vi.fn().mockResolvedValue(JSON.stringify(body ?? {})),
});

describe('tenantsApi helpers', () => {
  it('slugifies a display name and suffixes collisions', () => {
    expect(generateTenantAliasBase('Acme Corp')).toBe('acme-corp');
    expect(generateTenantAliasBase('Café')).toBe('cafe');
    expect(generateTenantAliasBase('!!!')).toBe('tenant');
    expect(generateUniqueTenantAlias('Acme Corp', [ACME])).toBe('acme-corp-2');
    expect(generateUniqueTenantAlias('Acme Corp', [ACME, { ...ACME, id: 'x', slug: 'acme-corp-2' }])).toBe(
      'acme-corp-3',
    );
  });

  it('rejects empty, overlong, and duplicate names', () => {
    expect(validateTenantDisplayName('')).toBe('Tenant name cannot be empty.');
    expect(validateTenantDisplayName('a'.repeat(51))).toContain('50');
    expect(validateTenantDisplayName('Acme')).toBeNull();
    expect(isDuplicateTenantName('acme corp', [ACME])).toBe(true);
    expect(isDuplicateTenantName('acme corp', [ACME], 't1')).toBe(false);
  });
});

describe('tenantsApi HTTP', () => {
  beforeEach(() => {
    vi.resetModules();
    getAccessToken.mockReset().mockReturnValue('access-token');
    resumeLoginAfterLogout.mockReset();
    vi.unstubAllGlobals();
  });

  it('lists tenants and fills missing slug/status', async () => {
    const { fetchTenants } = await import('./tenantsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 200,
        body: [
          { id: 't1', name: 'Acme Corp', slug: 'acme-corp', status: 'ACTIVE' },
          { id: 't2', name: 'Beta' },
        ],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const rows = await fetchTenants();
    expect(rows).toEqual([
      ACME,
      { id: 't2', name: 'Beta', slug: 't2', status: 'ACTIVE' },
    ]);
    expect(String(fetchMock.mock.calls[0][0])).toContain('/v1.0/m8flow/tenants');
  });

  it('creates via POST /tenant-realms with a unique slug', async () => {
    const { createTenant } = await import('./tenantsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 201,
        body: { id: 't9', alias: 'acme-corp-2', name: 'Acme Corp' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const created = await createTenant('Acme Corp', [ACME, BETA]);
    expect(created).toEqual({
      id: 't9',
      name: 'Acme Corp',
      slug: 'acme-corp-2',
      status: 'ACTIVE',
    });
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      slug: 'acme-corp-2',
      name: 'Acme Corp',
    });
    expect(String(fetchMock.mock.calls[0][0])).toContain('/v1.0/m8flow/tenant-realms');
  });

  it('renames via PUT /tenants/{id} with name only', async () => {
    const { updateTenantName } = await import('./tenantsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({ ok: true, status: 200, body: { message: 'ok', name: 'New' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await updateTenantName('t1', '  New  ');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/v1.0/m8flow/tenants/t1');
    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({ method: 'PUT' }));
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ name: 'New' });
  });

  it('surfaces backend detail on create conflict', async () => {
    const { createTenant } = await import('./tenantsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: false,
        status: 409,
        body: { detail: 'A tenant with this name already exists. Please choose a different name.' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(createTenant('Beta', [ACME])).rejects.toMatchObject({
      status: 409,
      serverMessage: 'A tenant with this name already exists. Please choose a different name.',
    });
  });
});

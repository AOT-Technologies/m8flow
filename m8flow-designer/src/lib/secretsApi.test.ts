import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './api';

const { getAccessToken, resumeLoginAfterLogout } = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  resumeLoginAfterLogout: vi.fn(),
}));

vi.mock('./auth', () => ({
  getAccessToken,
  resumeLoginAfterLogout,
}));

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

function firstUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return String(fetchMock.mock.calls[0][0]);
}

function firstInit(fetchMock: ReturnType<typeof vi.fn>): RequestInit {
  return fetchMock.mock.calls[0][1] as RequestInit;
}

const META = {
  id: 7,
  key: 'SMTP_PASSWORD',
  user_id: 3,
  created_at_in_seconds: 1,
  updated_at_in_seconds: 2,
  username: 'integrator',
};

describe('secretsApi', () => {
  beforeEach(() => {
    vi.resetModules();
    getAccessToken.mockReset().mockReturnValue('access-token');
    resumeLoginAfterLogout.mockReset();
    vi.unstubAllGlobals();
  });

  it('lists secrets with page, per_page, and optional tenantId', async () => {
    const { fetchSecrets } = await import('./secretsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 200,
        body: {
          results: [META],
          pagination: { count: 1, total: 1, pages: 1 },
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const listed = await fetchSecrets({ page: 2, perPage: 25, tenantId: 't1' });
    expect(listed.results).toHaveLength(1);
    expect(listed.results[0].key).toBe('SMTP_PASSWORD');
    expect(listed.results[0].username).toBe('integrator');
    expect(listed.pagination.total).toBe(1);
    expect(firstUrl(fetchMock)).toContain('/v1.0/secrets?');
    expect(firstUrl(fetchMock)).toContain('page=2');
    expect(firstUrl(fetchMock)).toContain('per_page=25');
    expect(firstUrl(fetchMock)).toContain('tenantId=t1');
    expect(listed.results[0]).not.toHaveProperty('value');
  });

  it('omits tenantId and pagination when not asked', async () => {
    const { fetchSecrets } = await import('./secretsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 200,
        body: { results: [], pagination: { count: 0, total: 0, pages: 0 } },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchSecrets();
    expect(firstUrl(fetchMock)).toMatch(/\/v1\.0\/secrets$/);
  });

  it('drops value if a list row accidentally includes it', async () => {
    const { fetchSecrets } = await import('./secretsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 200,
        body: {
          results: [{ ...META, value: 'should-not-leak' }],
          pagination: { count: 1, total: 1, pages: 1 },
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const listed = await fetchSecrets();
    expect(listed.results[0]).not.toHaveProperty('value');
  });

  it('gets metadata by key and never keeps a value field', async () => {
    const { fetchSecret } = await import('./secretsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 200,
        body: { ...META, value: 'nope' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const shown = await fetchSecret('SMTP_PASSWORD', 't2');
    expect(shown.key).toBe('SMTP_PASSWORD');
    expect(shown).not.toHaveProperty('value');
    expect(firstUrl(fetchMock)).toContain('/v1.0/secrets/SMTP_PASSWORD?tenantId=t2');
  });

  it('creates with { key, value } and returns metadata without the value', async () => {
    const { createSecret } = await import('./secretsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        ok: true,
        status: 201,
        body: { ...META, value: 'super-secret' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const created = await createSecret('SMTP_PASSWORD', 'super-secret', 't1');
    expect(created.key).toBe('SMTP_PASSWORD');
    expect(created).not.toHaveProperty('value');
    expect(firstUrl(fetchMock)).toContain('/v1.0/secrets?tenantId=t1');
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'POST' }));
    expect(JSON.parse(String(firstInit(fetchMock).body))).toEqual({
      key: 'SMTP_PASSWORD',
      value: 'super-secret',
    });
  });

  it('updates with { value } only', async () => {
    const { updateSecret } = await import('./secretsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({ ok: true, status: 200, body: { ok: true } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await updateSecret('SMTP_PASSWORD', 'rotated');
    expect(firstUrl(fetchMock)).toContain('/v1.0/secrets/SMTP_PASSWORD');
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'PUT' }));
    expect(JSON.parse(String(firstInit(fetchMock).body))).toEqual({ value: 'rotated' });
  });

  it('deletes by key', async () => {
    const { deleteSecret } = await import('./secretsApi');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({ ok: true, status: 200, body: { ok: true } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await deleteSecret('SMTP_PASSWORD', 't9');
    expect(firstUrl(fetchMock)).toContain('/v1.0/secrets/SMTP_PASSWORD?tenantId=t9');
    expect(firstInit(fetchMock)).toEqual(expect.objectContaining({ method: 'DELETE' }));
  });

  it('maps backend messages for user-facing errors', async () => {
    const { secretsErrorMessage } = await import('./secretsApi');
    const error = new ApiError('/v1.0/secrets', 403, 'POST', 'Not allowed to manage secrets');
    expect(secretsErrorMessage(error, 'Could not create secret.')).toBe(
      'Not allowed to manage secrets',
    );
    expect(secretsErrorMessage(new Error('network down'), 'Could not create secret.')).toBe(
      'network down',
    );
    expect(secretsErrorMessage({}, 'Could not create secret.')).toBe('Could not create secret.');
  });
});

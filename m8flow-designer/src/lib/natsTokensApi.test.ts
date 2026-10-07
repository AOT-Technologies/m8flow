import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getAccessToken, resumeLoginAfterLogout } = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  resumeLoginAfterLogout: vi.fn(),
}));

vi.mock('./auth', () => ({
  getAccessToken,
  resumeLoginAfterLogout,
}));

const okResponse = (body: unknown, status = 200) => ({
  ok: true,
  status,
  statusText: 'OK',
  json: vi.fn().mockResolvedValue(body),
  clone: vi.fn().mockReturnThis(),
  text: vi.fn().mockResolvedValue(JSON.stringify(body)),
});

describe('natsTokensApi', () => {
  beforeEach(() => {
    vi.resetModules();
    getAccessToken.mockReset().mockReturnValue('access-token');
    vi.unstubAllGlobals();
  });

  it('lists keys, scoping by tenantId only when given', async () => {
    const { fetchNatsApiKeys } = await import('./natsTokensApi');
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ keys: [{ id: 'abc', label: 'x' }] }));
    vi.stubGlobal('fetch', fetchMock);

    expect(await fetchNatsApiKeys('t1')).toEqual([{ id: 'abc', label: 'x' }]);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/v1\.0\/m8flow\/nats-tokens\?tenantId=t1$/);

    await fetchNatsApiKeys(null);
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/v1\.0\/m8flow\/nats-tokens$/);
  });

  it('treats a malformed list body as no keys', async () => {
    const { fetchNatsApiKeys } = await import('./natsTokensApi');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse({})));
    expect(await fetchNatsApiKeys()).toEqual([]);
  });

  it('POSTs the create body and returns the one-time token', async () => {
    const { createNatsApiKey } = await import('./natsTokensApi');
    const fetchMock = vi
      .fn()
      .mockResolvedValue(okResponse({ id: 'abc', label: 'Billing', token: 'm8f_abc.secret' }, 201));
    vi.stubGlobal('fetch', fetchMock);

    const created = await createNatsApiKey(
      { label: 'Billing', expiresInDays: null, scope: ['billing/paid'] },
      't1',
    );
    expect(created.token).toBe('m8f_abc.secret');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/v1\.0\/m8flow\/nats-tokens\?tenantId=t1$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({
      label: 'Billing',
      expiresInDays: null,
      scope: ['billing/paid'],
    });
  });

  it('DELETEs a single key by id', async () => {
    const { revokeNatsApiKey } = await import('./natsTokensApi');
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ revoked: true, id: 'abc' }));
    vi.stubGlobal('fetch', fetchMock);

    await revokeNatsApiKey('abc', 't1');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/v1\.0\/m8flow\/nats-tokens\/abc\?tenantId=t1$/);
    expect(init.method).toBe('DELETE');
  });
});

import { afterEach, describe, expect, it, vi } from 'vitest';

const { resumeLoginAfterLogout } = vi.hoisted(() => ({ resumeLoginAfterLogout: vi.fn() }));

vi.mock('./auth', () => ({
  getAccessToken: () => 'configured-version-token',
  resumeLoginAfterLogout,
}));

function jsonResponse(status: number, body: unknown = {}, apiVersion: string | null = '2.0') {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (apiVersion !== null) {
    headers.set('X-M8Flow-API-Version', apiVersion);
  }
  return new Response(JSON.stringify(body), {
    status,
    headers,
  });
}

describe('configured API version propagation', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
    resumeLoginAfterLogout.mockReset();
  });

  it('sends the configured V2 value on shared, refresh, and invitation requests', async () => {
    vi.stubEnv('VITE_API_VERSION', '2.0');
    vi.resetModules();

    const { apiGet, API_VERSION, API_VERSION_HEADER } = await import('./api');
    const { acceptInvitation, validateInvitation } = await import('./invitationsApi');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401))
      .mockResolvedValueOnce(jsonResponse(200))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))
      .mockResolvedValueOnce(jsonResponse(200, { email: 'user@example.com' }))
      .mockResolvedValueOnce(jsonResponse(200, { accepted: true }));
    vi.stubGlobal('fetch', fetchMock);

    expect(API_VERSION).toBe('2.0');
    await expect(apiGet('/v1.0/tasks')).resolves.toEqual({ ok: true });
    await validateInvitation('invitation-token');
    await acceptInvitation('invitation-token', 'password123');

    expect(fetchMock).toHaveBeenCalledTimes(5);
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init.headers).get(API_VERSION_HEADER)).toBe('2.0');
    }
  });

  it.each(['1.0', null] as const)(
    'rejects a V2 request when the backend reports %s',
    async (reportedVersion) => {
      vi.stubEnv('VITE_API_VERSION', '2.0');
      vi.resetModules();

      const { apiGet, ApiVersionMismatchError } = await import('./api');
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }, reportedVersion));
      vi.stubGlobal('fetch', fetchMock);

      await expect(apiGet('/v1.0/tasks')).rejects.toBeInstanceOf(ApiVersionMismatchError);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it('rejects a V1 request when the backend reports V2', async () => {
    vi.stubEnv('VITE_API_VERSION', '1.0');
    vi.resetModules();

    const { apiGet, ApiVersionMismatchError } = await import('./api');
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }, '2.0'));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/v1.0/tasks')).rejects.toBeInstanceOf(ApiVersionMismatchError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each(['1.0', null] as const)(
    'rejects a V2 invitation validation response when the backend reports %s',
    async (reportedVersion) => {
      vi.stubEnv('VITE_API_VERSION', '2.0');
      vi.resetModules();

      const { ApiVersionMismatchError } = await import('./api');
      const { validateInvitation } = await import('./invitationsApi');
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}, reportedVersion));
      vi.stubGlobal('fetch', fetchMock);

      await expect(validateInvitation('invitation-token')).rejects.toBeInstanceOf(
        ApiVersionMismatchError,
      );
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it.each(['1.0', null] as const)(
    'rejects a V2 invitation acceptance response when the backend reports %s',
    async (reportedVersion) => {
      vi.stubEnv('VITE_API_VERSION', '2.0');
      vi.resetModules();

      const { ApiVersionMismatchError } = await import('./api');
      const { acceptInvitation } = await import('./invitationsApi');
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}, reportedVersion));
      vi.stubGlobal('fetch', fetchMock);

      await expect(acceptInvitation('invitation-token', 'password123')).rejects.toBeInstanceOf(
        ApiVersionMismatchError,
      );
      expect(fetchMock).toHaveBeenCalledTimes(1);
    },
  );

  it('rejects a refresh response from a different API version without redirecting to login', async () => {
    vi.stubEnv('VITE_API_VERSION', '2.0');
    vi.resetModules();

    const { apiGet, ApiVersionMismatchError } = await import('./api');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401))
      .mockResolvedValueOnce(jsonResponse(200, {}, '1.0'));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/v1.0/tasks')).rejects.toBeInstanceOf(ApiVersionMismatchError);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(resumeLoginAfterLogout).not.toHaveBeenCalled();
  });
});

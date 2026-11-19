import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { resumeLoginAfterLogout } = vi.hoisted(() => ({ resumeLoginAfterLogout: vi.fn() }));
vi.mock('./auth', () => ({
  getAccessToken: () => 'editor-token',
  resumeLoginAfterLogout,
}));

const response = (status: number, body: unknown = {}) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  vi.resetModules();
  resumeLoginAfterLogout.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe('session refresh recovery', () => {
  it('keeps the page on refresh network failure and allows protected reads after recovery', async () => {
    const { apiGet, NetworkError } = await import('./api');
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(401))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200, { user: 'editor' }))
      .mockResolvedValueOnce(response(200, { tasks: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/v1.0/onboarding')).rejects.toBeInstanceOf(NetworkError);
    expect(resumeLoginAfterLogout).not.toHaveBeenCalled();
    await expect(apiGet('/v1.0/onboarding')).resolves.toEqual({ user: 'editor' });
    await expect(apiGet('/v1.0/tasks')).resolves.toEqual({ tasks: [] });
    expect(resumeLoginAfterLogout).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/refresh'))).toHaveLength(2);
    for (const [url, init] of fetchMock.mock.calls) {
      expect(init.credentials).toBe('include');
      if (!String(url).endsWith('/refresh')) {
        expect(new Headers(init.headers).get('Authorization')).toBe('Bearer editor-token');
      }
    }
  });

  it('shares a failing refresh between concurrent requests and clears it for a later retry', async () => {
    const { apiGet, NetworkError } = await import('./api');
    let failRefresh!: (error: unknown) => void;
    const refresh = new Promise<Response>((_, reject) => { failRefresh = reject; });
    const fetchMock = vi.fn((url: string) => String(url).endsWith('/refresh')
      ? refresh : Promise.resolve(response(401)));
    vi.stubGlobal('fetch', fetchMock);
    const results = Promise.allSettled([apiGet('/v1.0/onboarding'), apiGet('/v1.0/tasks')]);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    failRefresh(new TypeError('Load failed'));
    const settled = await results;
    for (const result of settled) {
      expect(result.status).toBe('rejected');
      if (result.status === 'rejected') expect(result.reason).toBeInstanceOf(NetworkError);
    }
    expect(resumeLoginAfterLogout).not.toHaveBeenCalled();
    fetchMock.mockImplementation(() => Promise.resolve(response(200, { recovered: true })));
    await expect(apiGet('/v1.0/tasks')).resolves.toEqual({ recovered: true });
  });

  it('refreshes successfully and retries a request once', async () => {
    const { apiGet } = await import('./api');
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200, { ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiGet('/v1.0/tasks')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(resumeLoginAfterLogout).not.toHaveBeenCalled();
  });

  it('retains the login redirect for an explicit authentication failure', async () => {
    const { apiGet, ApiError } = await import('./api');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(401)));
    await expect(apiGet('/v1.0/tasks')).rejects.toBeInstanceOf(ApiError);
    expect(resumeLoginAfterLogout).toHaveBeenCalledTimes(1);
  });

  it('passes refresh programming errors through without redirecting', async () => {
    const { apiGet } = await import('./api');
    const error = new TypeError('Invalid URL');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(401)).mockRejectedValueOnce(error));
    await expect(apiGet('/v1.0/tasks')).rejects.toBe(error);
    expect(resumeLoginAfterLogout).not.toHaveBeenCalled();
  });
});

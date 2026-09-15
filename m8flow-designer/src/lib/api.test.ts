import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./auth', () => ({
  getAccessToken: () => 'test-token',
  resumeLoginAfterLogout: vi.fn(),
}));

import { apiGet, ApiError } from './api';

function makeResponse(opts: { ok: boolean; status: number; body?: unknown }) {
  return {
    ok: opts.ok,
    status: opts.status,
    json: async () => opts.body,
    clone() {
      return makeResponse(opts);
    },
  };
}

describe('apiGet', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('deduplicates concurrent GETs to the same path into a single fetch', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeResponse({ ok: true, status: 200, body: { n: 1 } }));
    vi.stubGlobal('fetch', fetchMock);

    const [a, b] = await Promise.all([
      apiGet('/v1.0/m8flow/home-stats'),
      apiGet('/v1.0/m8flow/home-stats'),
    ]);

    expect(a).toEqual({ n: 1 });
    expect(b).toEqual({ n: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not merge concurrent GETs for different paths', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      const path = String(url);
      if (path.includes('home-stats')) {
        return Promise.resolve(makeResponse({ ok: true, status: 200, body: { kind: 'stats' } }));
      }
      return Promise.resolve(makeResponse({ ok: true, status: 200, body: { kind: 'tasks' } }));
    });
    vi.stubGlobal('fetch', fetchMock);

    const [stats, tasks] = await Promise.all([
      apiGet<{ kind: string }>('/v1.0/m8flow/home-stats'),
      apiGet<{ kind: string }>('/v1.0/m8flow/home-my-tasks'),
    ]);

    expect(stats).toEqual({ kind: 'stats' });
    expect(tasks).toEqual({ kind: 'tasks' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('issues a new GET after the previous request for the same path has settled', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(makeResponse({ ok: true, status: 200, body: { n: 1 } }))
      .mockResolvedValueOnce(makeResponse({ ok: true, status: 200, body: { n: 2 } }));
    vi.stubGlobal('fetch', fetchMock);

    expect(await apiGet('/v1.0/m8flow/home-stats')).toEqual({ n: 1 });
    expect(await apiGet('/v1.0/m8flow/home-stats')).toEqual({ n: 2 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not attempt a refresh for non-401 failures', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(makeResponse({ ok: false, status: 404 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/v1.0/m8flow/process-models')).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

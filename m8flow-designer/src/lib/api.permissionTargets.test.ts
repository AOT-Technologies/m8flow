import { afterEach, describe, expect, it, vi } from 'vitest';
import { pathForApiVersion } from './apiVersionConfig';

afterEach(() => {
  vi.resetModules();
  vi.doUnmock('./apiVersion');
  vi.doUnmock('./auth');
  vi.unstubAllGlobals();
});

describe.each(['1.0', '2.0'])('permissions-check targets for API %s', (version) => {
  it('versions the endpoint while keeping resource URIs version-neutral', async () => {
    vi.doMock('./apiVersion', () => ({
      API_VERSION: version,
      API_VERSION_PREFIX: `/v${version}`,
      apiVersionPath: (path: string) => pathForApiVersion(path, version),
    }));
    vi.doMock('./auth', () => ({
      getAccessToken: () => 'test-token',
      resumeLoginAfterLogout: vi.fn(),
    }));

    const targetUris = {
      '/task-data/42': ['GET'],
      '/process-models/approval:leave-request/publish': ['POST'],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ results: {} }), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { checkPermissions } = await import('./api');
    await expect(checkPermissions(targetUris)).resolves.toEqual({});

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/v${version}/permissions-check`);
    expect(JSON.parse(String(init.body))).toEqual({ requests_to_check: targetUris });
    expect(String(init.body)).not.toMatch(/\/v\d+(?:\.\d+)?\//);
  });
});

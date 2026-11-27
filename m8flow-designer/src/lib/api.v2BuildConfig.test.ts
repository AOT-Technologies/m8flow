import { afterEach, describe, expect, it, vi } from 'vitest';

import { pathForApiVersion, resolveApiVersionBuildConfig } from './apiVersionConfig';

const response = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status });

afterEach(() => {
  vi.resetModules();
  vi.doUnmock('./apiVersion');
  vi.doUnmock('./auth');
  vi.unstubAllGlobals();
});

describe('API requests built with configured API versions', () => {
  function mockConfiguredApiVersion(apiVersion: string): void {
    vi.doMock('./apiVersion', () => ({
      API_VERSION: apiVersion,
      API_VERSION_PREFIX: `/v${apiVersion}`,
      apiVersionPath: (path: string) => pathForApiVersion(path, apiVersion),
    }));
  }

  async function expectVersionedRequests(apiVersion: string): Promise<void> {
    mockConfiguredApiVersion(apiVersion);
    vi.doMock('./auth', async (importOriginal) => {
      const actual = await importOriginal<typeof import('./auth')>();
      return {
        ...actual,
        getAccessToken: () => 'test-token',
        resumeLoginAfterLogout: vi.fn(),
      };
    });

    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200, { tasks: [] }))
      .mockResolvedValueOnce(response(200, { email: 'user@example.com' }));
    vi.stubGlobal('fetch', fetchMock);

    const { apiGet } = await import('./api');
    const { validateInvitation } = await import('./invitationsApi');
    const { templateFileDownloadUrl } = await import('./templatesApi');

    await expect(apiGet('/tasks')).resolves.toEqual({ tasks: [] });
    await expect(validateInvitation('invite-token')).resolves.toEqual({ email: 'user@example.com' });
    expect(templateFileDownloadUrl(12, 'diagram.bpmn')).toContain(
      `/v${apiVersion}/m8flow/templates/12/files/diagram.bpmn`,
    );

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      expect.stringContaining(`/v${apiVersion}/tasks`),
      expect.stringContaining(`/v${apiVersion}/refresh`),
      expect.stringContaining(`/v${apiVersion}/tasks`),
      expect.stringContaining(`/v${apiVersion}/m8flow/invitations/validate?token=invite-token`),
    ]);

    const { login, logout } = await import('./auth');
    const location = {
      href: 'http://localhost:6853/',
      origin: 'http://localhost:6853',
      pathname: '/',
      search: '',
    };
    vi.stubGlobal('location', location);
    login({ redirectUrl: 'http://localhost:6853/' });
    expect(location.href).toContain(`http://localhost:6840/v${apiVersion}/login?`);
    logout();
    expect(location.href).toContain(`http://localhost:6840/v${apiVersion}/logout?`);
  }

  it('defaults to V1 and uses it for API, retry, invitation, file URL, and auth redirect paths', async () => {
    const apiVersion = resolveApiVersionBuildConfig({ M8FLOW_API_VERSION: '' }).version;
    expect(apiVersion).toBe('1.0');
    await expectVersionedRequests(apiVersion);
  });

  it('uses the configured V2 build value for API, retry, invitation, file URL, and auth redirect paths', async () => {
    const apiVersion = resolveApiVersionBuildConfig({ M8FLOW_API_VERSION: '2.0' }).version;
    expect(apiVersion).toBe('2.0');
    await expectVersionedRequests(apiVersion);
  });

});

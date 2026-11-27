import { afterEach, describe, expect, it, vi } from 'vitest';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

import { pathForApiVersion, SUPPORTED_API_VERSIONS } from './apiVersionConfig';

const response = (status: number, body: unknown = {}) =>
  new Response(JSON.stringify(body), { status });

afterEach(() => {
  vi.resetModules();
  vi.doUnmock('./apiVersion');
  vi.doUnmock('./auth');
  vi.unstubAllGlobals();
});

describe('API requests built with configured API versions', () => {
  async function loadViteConfiguredVersion(version: string | null = '2.0'): Promise<string> {
    const environment: Record<string, string | undefined> = {
      ...process.env,
      M8FLOW_API_VERSION: version ?? '',
    };
    if (version === null) {
      // Empty process values override any developer .env values loaded by Vite.
      environment.VITE_API_VERSION = '';
    } else {
      delete environment.VITE_API_VERSION;
    }
    const script = [
      "import { loadConfigFromFile } from 'vite';",
      "const loaded = await loadConfigFromFile({ command: 'build', mode: 'production' }, 'vite.config.ts', process.cwd());",
      "console.log(JSON.stringify(loaded.config.define['import.meta.env.VITE_API_VERSION']));",
    ].join('\n');
    const output = execFileSync(process.execPath, ['--input-type=module', '-e', script], {
      cwd: resolve(process.cwd()),
      env: environment,
      encoding: 'utf8',
    });
    const definedLiteral = JSON.parse(output.trim()) as string;
    expect(definedLiteral).toBe(JSON.stringify(version ?? '1.0'));
    return JSON.parse(definedLiteral) as string;
  }

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
    const apiVersion = await loadViteConfiguredVersion(null);
    expect(apiVersion).toBe('1.0');
    await expectVersionedRequests(apiVersion);
  });

  it('uses V2 from the real Vite config for API, retry, invitation, file URL, and auth redirect paths', async () => {
    const apiVersion = await loadViteConfiguredVersion('2.0');
    expect(apiVersion).toBe('2.0');
    await expectVersionedRequests(apiVersion);
  });

  it('proxies every supported API version to the backend in the real Vite config', () => {
    const script = [
      "import { loadConfigFromFile } from 'vite';",
      "const loaded = await loadConfigFromFile({ command: 'serve', mode: 'development' }, 'vite.config.ts', process.cwd());",
      "console.log(JSON.stringify(Object.keys(loaded.config.server.proxy)));",
    ].join('\n');
    const output = execFileSync(process.execPath, ['--input-type=module', '-e', script], {
      cwd: resolve(process.cwd()),
      env: process.env,
      encoding: 'utf8',
    });

    expect(JSON.parse(output.trim())).toEqual(
      SUPPORTED_API_VERSIONS.map((version) => `/v${version}`),
    );
  });

});

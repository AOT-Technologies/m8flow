import { afterEach, describe, expect, it, vi } from 'vitest';

const encodeJwtPayload = (payload: Record<string, unknown>) => {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const body = btoa(JSON.stringify(payload));
  return `${header}.${body}.signature`;
};

const stubAuthCookies = (accessPayload: Record<string, unknown>) => {
  const accessToken = encodeJwtPayload(accessPayload);
  vi.stubGlobal('document', {
    cookie: `access_token=${accessToken}; id_token=ignored`,
  } as Document);
};

const TASK_GUID = '12345678-1234-1234-1234-123456789abc';

const stubLocation = (href: string) => {
  const url = new URL(href);
  vi.stubGlobal('location', {
    href: url.toString(),
    origin: url.origin,
    pathname: url.pathname,
    search: url.search,
    hostname: url.hostname,
    port: url.port,
    replace: vi.fn(),
  } as unknown as Location);
};

const loadUserService = async (href: string) => {
  vi.resetModules();
  vi.unstubAllGlobals();
  stubLocation(href);
  return (await import('./UserService')).default;
};

describe('UserService.doLogin', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    localStorage.clear();
    document.cookie = 'm8flow_auth_realm=; Max-Age=0; Path=/';
  });

  it('uses the current absolute location without double encoding when redirectUrl is omitted', async () => {
    const currentHref = `http://localhost:8001/tasks/42/${TASK_GUID}?tab=details`;
    const UserService = await loadUserService(currentHref);

    UserService.doLogin();

    expect(globalThis.location.href).toBe(
      `http://localhost:8000/v1.0/login?redirect_url=${encodeURIComponent(currentHref)}&process_instance_id=42&task_guid=${TASK_GUID}`,
    );
  });

  it('normalizes relative task redirects before building the login URL', async () => {
    const UserService = await loadUserService('http://localhost:8001/login');

    UserService.doLogin(undefined, `/tasks/24/${TASK_GUID}?tab=details`);

    expect(globalThis.location.href).toBe(
      `http://localhost:8000/v1.0/login?redirect_url=${encodeURIComponent(`http://localhost:8001/tasks/24/${TASK_GUID}?tab=details`)}&process_instance_id=24&task_guid=${TASK_GUID}`,
    );
  });

  it('persists the selected authentication realm when building the login URL', async () => {
    const UserService = await loadUserService('http://localhost:8001/login');

    UserService.doLogin({ identifier: 'ops-admin', label: 'Master', uri: '' }, '/tenants');

    expect(localStorage.getItem('m8flow_auth_realm')).toBe('ops-admin');
    expect(document.cookie).toContain('m8flow_auth_realm=ops-admin');
  });

  it('returns all organization memberships from the id token', async () => {
    const UserService = await loadUserService('http://localhost:8001/');
    document.cookie = [
      'id_token=',
      [
        btoa(JSON.stringify({ alg: 'none', typ: 'JWT' })),
        btoa(
          JSON.stringify({
            organization: {
              'tenant-a': { id: 'tenant-a-id', name: 'Tenant A' },
              'tenant-b': { id: 'tenant-b-id' },
            },
          }),
        ),
        '',
      ].join('.'),
      '; Path=/',
    ].join('');

    expect(UserService.getOrganizationMemberships()).toEqual([
      { alias: 'tenant-a', id: 'tenant-a-id', name: 'Tenant A' },
      { alias: 'tenant-b', id: 'tenant-b-id', name: null },
    ]);
  });

  it('returns organization memberships when Keycloak serializes the claim as an alias list', async () => {
    const UserService = await loadUserService('http://localhost:8001/');
    document.cookie = [
      'id_token=',
      [
        btoa(JSON.stringify({ alg: 'none', typ: 'JWT' })),
        btoa(
          JSON.stringify({
            organization: ['tenant-a', 'tenant-b'],
          }),
        ),
        '',
      ].join('.'),
      '; Path=/',
    ].join('');

    expect(UserService.getOrganizationMemberships()).toEqual([
      { alias: 'tenant-a', id: null, name: null },
      { alias: 'tenant-b', id: null, name: null },
    ]);
  });

  it('falls back to the stored tenant name when the token is multi-organization', async () => {
    const UserService = await loadUserService('http://localhost:8001/');
    localStorage.setItem('m8flow_tenant', 'tenant-b');
    document.cookie = [
      'id_token=',
      [
        btoa(JSON.stringify({ alg: 'none', typ: 'JWT' })),
        btoa(
          JSON.stringify({
            organization: {
              'tenant-a': { id: 'tenant-a-id' },
              'tenant-b': { id: 'tenant-b-id' },
            },
          }),
        ),
        '',
      ].join('.'),
      '; Path=/',
    ].join('');

    expect(UserService.getTenantName()).toBe('tenant-b');
  });
});

const loadUserServiceWithAuth = async (
  href: string,
  accessPayload: Record<string, unknown>,
) => {
  vi.resetModules();
  stubLocation(href);
  stubAuthCookies(accessPayload);
  return (await import('./UserService')).default;
};

describe('UserService.isSuperAdmin', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it('returns true when access_token has top-level super-admin role', async () => {
    const UserService = await loadUserServiceWithAuth('http://localhost:8001/', {
      roles: ['super-admin'],
    });
    expect(UserService.isSuperAdmin()).toBe(true);
  });

  it('returns true when access_token has super-admin in groups claim', async () => {
    const UserService = await loadUserServiceWithAuth('http://localhost:8001/', {
      groups: ['/super-admin'],
    });
    expect(UserService.isSuperAdmin()).toBe(true);
  });

  it('returns false for non-super-admin roles', async () => {
    const UserService = await loadUserServiceWithAuth('http://localhost:8001/', {
      roles: ['editor'],
    });
    expect(UserService.isSuperAdmin()).toBe(false);
  });
});

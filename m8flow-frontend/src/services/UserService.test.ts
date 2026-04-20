import { afterEach, describe, expect, it, vi } from 'vitest';

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
});

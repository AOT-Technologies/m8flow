import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getActiveTenantDisplayLabel,
  getOrganizationMemberships,
  getSelectedTenantId,
  login,
  loginAsPlatformAdmin,
  shouldShowTenantSelectionGate,
} from './auth';

function encodeJwt(payload: Record<string, unknown>): string {
  const body = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `eyJhbGciOiJub25lIn0.${body}.sig`;
}

function setCookie(name: string, value: string): void {
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/`;
}

function clearCookie(name: string): void {
  document.cookie = `${name}=; Max-Age=0; Path=/`;
}

function clearAuthCookies(): void {
  clearCookie('access_token');
  clearCookie('id_token');
  clearCookie('authentication_identifier');
  clearCookie('m8flow_selected_tenant');
}

const futureExp = Math.floor(Date.now() / 1000) + 3600;

describe('auth tenant gate', () => {
  afterEach(() => {
    clearAuthCookies();
    vi.unstubAllGlobals();
    try {
      localStorage.clear();
    } catch {
      /* ignore */
    }
  });

  it('parses organization memberships from a Keycloak object claim', () => {
    setCookie(
      'id_token',
      encodeJwt({
        exp: futureExp,
        organization: {
          acme: { id: 'tenant-acme', name: 'Acme' },
          other: { id: 'tenant-other' },
        },
      }),
    );

    expect(getOrganizationMemberships()).toEqual([
      { alias: 'acme', id: 'tenant-acme', name: 'Acme' },
      { alias: 'other', id: 'tenant-other', name: null },
    ]);
  });

  it('does not treat localStorage as tenant finalization', () => {
    setCookie('access_token', encodeJwt({ exp: futureExp, preferred_username: 'editor' }));
    localStorage.setItem('m8flow_tenant', 'acme');
    localStorage.setItem('m8f_tenant_id', 'tenant-acme');

    expect(getSelectedTenantId()).toBeNull();
    expect(getActiveTenantDisplayLabel()).toBeNull();
    expect(shouldShowTenantSelectionGate('/')).toBe(true);
    expect(shouldShowTenantSelectionGate('/processes')).toBe(true);
  });

  it('shows the gate until the selected-tenant cookie is set', () => {
    setCookie('access_token', encodeJwt({ exp: futureExp, preferred_username: 'editor' }));
    expect(shouldShowTenantSelectionGate('/')).toBe(true);

    setCookie('m8flow_selected_tenant', 'tenant-acme');
    expect(shouldShowTenantSelectionGate('/')).toBe(false);
    expect(shouldShowTenantSelectionGate('/tenant')).toBe(true);
  });

  it('skips the cookie gate for super-admin and master-realm sessions', () => {
    setCookie('access_token', encodeJwt({ exp: futureExp, roles: ['super-admin'] }));
    expect(shouldShowTenantSelectionGate('/')).toBe(false);

    clearCookie('access_token');
    setCookie('access_token', encodeJwt({ exp: futureExp, preferred_username: 'ops' }));
    setCookie('authentication_identifier', 'master');
    expect(shouldShowTenantSelectionGate('/')).toBe(false);
  });

  it('does not intercept accept-invitation', () => {
    expect(shouldShowTenantSelectionGate('/accept-invitation')).toBe(false);
    expect(shouldShowTenantSelectionGate('/accept-invitation/')).toBe(false);
  });

  it('labels the active tenant from the cookie, using membership name when present', () => {
    setCookie(
      'id_token',
      encodeJwt({
        exp: futureExp,
        organization: {
          acme: { id: 'tenant-acme', name: 'Acme Corp' },
          other: { id: 'tenant-other', name: 'Other' },
        },
      }),
    );
    setCookie('m8flow_selected_tenant', 'tenant-acme');
    expect(getActiveTenantDisplayLabel()).toBe('Acme Corp');

    setCookie('m8flow_selected_tenant', 'other');
    expect(getActiveTenantDisplayLabel()).toBe('Other');
  });

  it('falls back to the cookie value when memberships have no display name', () => {
    setCookie('m8flow_selected_tenant', 'tenant-orphan');
    expect(getActiveTenantDisplayLabel()).toBe('tenant-orphan');
  });

  it('uses directory membership names when the JWT claim has no name', () => {
    setCookie('m8flow_selected_tenant', 'tenant-acme');
    expect(getActiveTenantDisplayLabel()).toBe('tenant-acme');
    expect(
      getActiveTenantDisplayLabel([
        { alias: 'acme', id: 'tenant-acme', name: 'Acme Corp' },
      ]),
    ).toBe('Acme Corp');
  });

  it('builds a tenant finalization login URL without copying a JWT tenant id', () => {
    const loc = {
      href: 'http://localhost:6853/tenant',
      origin: 'http://localhost:6853',
      pathname: '/tenant',
      search: '',
    };
    vi.stubGlobal('location', loc);

    login({
      authenticationIdentifier: 'm8flow',
      tenant: 'acme',
      tenantFinalization: true,
      redirectUrl: 'http://localhost:6853/',
    });

    expect(loc.href).toContain('/v1.0/login?');
    expect(loc.href).toContain('tenant=acme');
    expect(loc.href).toContain('tenant_finalization=1');
    expect(loc.href).toContain(`redirect_url=${encodeURIComponent('http://localhost:6853/')}`);
    expect(document.cookie).not.toContain('m8flow_selected_tenant=');
  });

  it('sends platform-admin login to the tenant registry', () => {
    const loc = {
      href: 'http://localhost:6853/',
      origin: 'http://localhost:6853',
      pathname: '/',
      search: '',
    };
    vi.stubGlobal('location', loc);

    loginAsPlatformAdmin();

    expect(loc.href).toContain('/v1.0/login?');
    expect(loc.href).toContain('authentication_identifier=master');
    expect(loc.href).toContain(`redirect_url=${encodeURIComponent('http://localhost:6853/tenants')}`);
  });
});

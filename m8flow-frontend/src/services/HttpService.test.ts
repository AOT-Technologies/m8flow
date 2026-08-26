import { waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  getAccessToken,
  isLoggedIn,
  isSuperAdmin,
  isPublicUser,
  redirectToLogin,
} = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  isLoggedIn: vi.fn(),
  isSuperAdmin: vi.fn(),
  isPublicUser: vi.fn(),
  redirectToLogin: vi.fn(),
}));

const { getStoredGlobalTenantId } = vi.hoisted(() => ({
  getStoredGlobalTenantId: vi.fn(),
}));

vi.mock('./UserService', () => ({
  default: {
    getAccessToken,
    isLoggedIn,
    isSuperAdmin,
    isPublicUser,
    redirectToLogin,
  },
}));

vi.mock('../contexts/GlobalTenantContext', () => ({
  getStoredGlobalTenantId,
}));

import { getBasicHeaders } from './HttpService';
import HttpService from './HttpService';

const makeResponse = ({
  body,
  ok,
  status,
  statusText = '',
}: {
  body: string;
  ok: boolean;
  status: number;
  statusText?: string;
}) => ({
  ok,
  status,
  statusText,
  text: vi.fn().mockResolvedValue(body),
});

describe('HttpService.getBasicHeaders', () => {
  beforeEach(() => {
    getAccessToken.mockReset();
    isLoggedIn.mockReset();
    isSuperAdmin.mockReset();
    isPublicUser.mockReset();
    redirectToLogin.mockReset();
    getStoredGlobalTenantId.mockReset();
    vi.unstubAllGlobals();
  });

  it('sends the bearer token whenever an access token cookie exists', () => {
    getAccessToken.mockReturnValue('stale-access-token');
    isLoggedIn.mockReturnValue(false);

    expect(getBasicHeaders()).toEqual({
      Authorization: 'Bearer stale-access-token',
    });
  });

  it('omits the bearer token when no access token cookie exists', () => {
    getAccessToken.mockReturnValue(null);

    expect(getBasicHeaders()).toEqual({});
  });
});

describe('HttpService.makeCallToBackend', () => {
  beforeEach(() => {
    getAccessToken.mockReset();
    isLoggedIn.mockReset();
    isSuperAdmin.mockReset();
    isPublicUser.mockReset();
    redirectToLogin.mockReset();
    getStoredGlobalTenantId.mockReset();
    vi.unstubAllGlobals();
  });

  it('retries a GET once before redirecting when the first request gets a 401', async () => {
    getAccessToken.mockReturnValue('access-token');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        makeResponse({
          body: '{"message":"expired"}',
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          body: '{"ok":true}',
          ok: true,
          status: 200,
          statusText: 'OK',
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    const successCallback = vi.fn();

    HttpService.makeCallToBackend({
      path: '/v1.0/m8flow/tenants',
      successCallback,
    });

    await waitFor(() => {
      expect(successCallback).toHaveBeenCalledWith({ ok: true });
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(redirectToLogin).not.toHaveBeenCalled();
  });

  it('redirects after a second GET 401', async () => {
    getAccessToken.mockReturnValue('access-token');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        makeResponse({
          body: '{"message":"expired"}',
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }),
      )
      .mockResolvedValueOnce(
        makeResponse({
          body: '{"message":"still expired"}',
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    HttpService.makeCallToBackend({
      path: '/v1.0/m8flow/tenants',
      successCallback: vi.fn(),
    });

    await waitFor(() => {
      expect(redirectToLogin).toHaveBeenCalledTimes(1);
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not retry non-GET requests', async () => {
    getAccessToken.mockReturnValue('access-token');
    isSuperAdmin.mockReturnValue(false);
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        body: '{"message":"expired"}',
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    HttpService.makeCallToBackend({
      path: '/v1.0/m8flow/tenant-realms',
      httpMethod: 'POST',
      postBody: { slug: 'tenant-a', name: 'Tenant A' },
      successCallback: vi.fn(),
    });

    await waitFor(() => {
      expect(redirectToLogin).toHaveBeenCalledTimes(1);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('adds the selected tenant header for super-admin mutating requests', async () => {
    getAccessToken.mockReturnValue('access-token');
    isSuperAdmin.mockReturnValue(true);
    getStoredGlobalTenantId.mockReturnValue('tenant-42');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        body: '{"ok":true}',
        ok: true,
        status: 200,
        statusText: 'OK',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const successCallback = vi.fn();
    HttpService.makeCallToBackend({
      path: '/v1.0/process-groups',
      httpMethod: 'POST',
      postBody: { id: 'finance' },
      successCallback,
    });

    await waitFor(() => {
      expect(successCallback).toHaveBeenCalledWith({ ok: true });
    });

    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer access-token');
    expect(headers.get('X-M8Flow-Tenant-Id')).toBe('tenant-42');
  });

  it('does not add the selected tenant header for GET requests', async () => {
    getAccessToken.mockReturnValue('access-token');
    isSuperAdmin.mockReturnValue(true);
    getStoredGlobalTenantId.mockReturnValue('tenant-42');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        body: '{"ok":true}',
        ok: true,
        status: 200,
        statusText: 'OK',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const successCallback = vi.fn();
    HttpService.makeCallToBackend({
      path: '/v1.0/process-groups',
      httpMethod: 'GET',
      successCallback,
    });

    await waitFor(() => {
      expect(successCallback).toHaveBeenCalledWith({ ok: true });
    });

    const headers = fetchMock.mock.calls[0][1].headers as Headers;
    expect(headers.get('X-M8Flow-Tenant-Id')).toBeNull();
  });

  it('normalizes RFC 7807 error payloads so failure callbacks always receive a message', async () => {
    getAccessToken.mockReturnValue('access-token');
    const fetchMock = vi.fn().mockResolvedValue(
      makeResponse({
        body: JSON.stringify({
          type: 'about:blank',
          title: 'vault_secret_value_missing',
          detail: 'Unable to locate the Vault secret value for key: SMTP_USER.',
          status: 404,
          error_code: 'vault_secret_value_missing',
        }),
        ok: false,
        status: 404,
        statusText: 'Not Found',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const failureCallback = vi.fn();

    HttpService.makeCallToBackend({
      path: '/tasks/123/task-1',
      httpMethod: 'PUT',
      postBody: { approved: true },
      successCallback: vi.fn(),
      failureCallback,
    });

    await waitFor(() => {
      expect(failureCallback).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'vault_secret_value_missing',
          detail: 'Unable to locate the Vault secret value for key: SMTP_USER.',
          message: 'Unable to locate the Vault secret value for key: SMTP_USER.',
        }),
      );
    });
  });
});

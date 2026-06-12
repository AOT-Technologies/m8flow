import { waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  getAccessToken,
  isLoggedIn,
  isPublicUser,
  redirectToLogin,
} = vi.hoisted(() => ({
  getAccessToken: vi.fn(),
  isLoggedIn: vi.fn(),
  isPublicUser: vi.fn(),
  redirectToLogin: vi.fn(),
}));

vi.mock('./UserService', () => ({
  default: {
    getAccessToken,
    isLoggedIn,
    isPublicUser,
    redirectToLogin,
  },
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
    isPublicUser.mockReset();
    redirectToLogin.mockReset();
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
    isPublicUser.mockReset();
    redirectToLogin.mockReset();
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
});

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

describe('HttpService.getBasicHeaders', () => {
  beforeEach(() => {
    getAccessToken.mockReset();
    isLoggedIn.mockReset();
    isPublicUser.mockReset();
    redirectToLogin.mockReset();
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

import { describe, expect, it } from 'vitest';
import { resolveContainerContentState } from './containerContentState';

describe('resolveContainerContentState', () => {
  it('redirects an expired session on a protected route to session recovery', () => {
    expect(
      resolveContainerContentState({
        backendIsUp: true,
        canAccessFrontend: false,
        isLoggedIn: false,
        pathname: '/tenants',
      }),
    ).toBe('session-expired-recovery');
  });

  it('keeps the login route active when the session is expired there', () => {
    expect(
      resolveContainerContentState({
        backendIsUp: true,
        canAccessFrontend: false,
        isLoggedIn: false,
        pathname: '/login',
      }),
    ).toBe('routes');
  });

  it('shows access denied when a logged-in user lacks frontend access', () => {
    expect(
      resolveContainerContentState({
        backendIsUp: true,
        canAccessFrontend: false,
        isLoggedIn: true,
        pathname: '/tenants',
      }),
    ).toBe('frontend-access-denied');
  });

  it('shows backend-down when the health check fails', () => {
    expect(
      resolveContainerContentState({
        backendIsUp: false,
        canAccessFrontend: true,
        isLoggedIn: true,
        pathname: '/',
      }),
    ).toBe('backend-down');
  });

  it('returns routes when the frontend is accessible', () => {
    expect(
      resolveContainerContentState({
        backendIsUp: true,
        canAccessFrontend: true,
        isLoggedIn: false,
        pathname: '/',
      }),
    ).toBe('routes');
  });
});

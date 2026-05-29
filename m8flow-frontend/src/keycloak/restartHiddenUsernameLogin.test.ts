import { describe, expect, it, vi } from 'vitest';

import {
  handleManualHiddenUsernameRestart,
  restartHiddenUsernameLogin,
} from '../../../m8flow-backend/keycloak/themes/m8flow/login/resources/js/restartHiddenUsernameLogin.js';

const createStorage = (initialValues: Record<string, string> = {}) => {
  const values = new Map(Object.entries(initialValues));

  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
};

describe('restartHiddenUsernameLogin theme helper', () => {
  it('tries the same restart URL twice before falling back to the manual recovery action', () => {
    document.body.innerHTML =
      '<div id="m8f-hidden-username-login-fallback" hidden></div>';
    const restartUrl = 'http://localhost:7002/realms/m8flow/login-actions/restart';
    const marker = {
      getAttribute: vi.fn((attribute: string) => {
        if (attribute === 'data-login-restart-url') {
          return restartUrl;
        }
        if (attribute === 'data-login-restart-fallback-id') {
          return 'm8f-hidden-username-login-fallback';
        }
        return null;
      }),
    };
    const locationObject = { replace: vi.fn() };
    const storage = createStorage();
    const fallback = document.getElementById('m8f-hidden-username-login-fallback') as HTMLDivElement;

    expect(restartHiddenUsernameLogin(marker as unknown as Element, locationObject, storage)).toBe(true);
    expect(restartHiddenUsernameLogin(marker as unknown as Element, locationObject, storage)).toBe(true);
    expect(restartHiddenUsernameLogin(marker as unknown as Element, locationObject, storage)).toBe(false);
    expect(locationObject.replace).toHaveBeenCalledTimes(2);
    expect(fallback.hidden).toBe(false);
  });

  it('auto-detects the username-only login marker rendered by the theme fallback page', () => {
    document.body.innerHTML =
      '<div id="m8f-username-only-login" data-login-restart-url="http://localhost:7002/restart"></div>';
    const locationObject = { replace: vi.fn() };
    const storage = createStorage();

    expect(restartHiddenUsernameLogin(undefined, locationObject, storage)).toBe(true);
    expect(locationObject.replace).toHaveBeenCalledWith('http://localhost:7002/restart');
  });

  it('restarts the login flow once when Keycloak renders the hidden-username step', () => {
    const marker = {
      getAttribute: vi.fn().mockReturnValue('http://localhost:7002/realms/m8flow/login-actions/restart'),
    };
    const locationObject = { replace: vi.fn() };
    const storage = createStorage();

    expect(restartHiddenUsernameLogin(marker as unknown as Element, locationObject, storage)).toBe(true);
    expect(locationObject.replace).toHaveBeenCalledWith(
      'http://localhost:7002/realms/m8flow/login-actions/restart',
    );
    expect(storage.getItem('m8flow-hidden-username-login-restart-url')).toBe(
      JSON.stringify({
        restartUrl: 'http://localhost:7002/realms/m8flow/login-actions/restart',
        attempts: 1,
      }),
    );
  });

  it('shows the manual fallback when the restart URL has already hit the retry limit', () => {
    document.body.innerHTML =
      '<div id="m8f-hidden-username-login-fallback" hidden></div>';
    const restartUrl = 'http://localhost:7002/realms/m8flow/login-actions/restart';
    const marker = {
      getAttribute: vi.fn((attribute: string) => {
        if (attribute === 'data-login-restart-url') {
          return restartUrl;
        }
        if (attribute === 'data-login-restart-fallback-id') {
          return 'm8f-hidden-username-login-fallback';
        }
        return null;
      }),
    };
    const locationObject = { replace: vi.fn() };
    const storage = createStorage({
      'm8flow-hidden-username-login-restart-url': JSON.stringify({
        restartUrl,
        attempts: 2,
      }),
    });
    const fallback = document.getElementById('m8f-hidden-username-login-fallback') as HTMLDivElement;

    expect(restartHiddenUsernameLogin(marker as unknown as Element, locationObject, storage)).toBe(false);
    expect(locationObject.replace).not.toHaveBeenCalled();
    expect(fallback.hidden).toBe(false);
  });

  it('clears the restart guard after the normal combined login page is shown again', () => {
    const storage = createStorage({
      'm8flow-hidden-username-login-restart-url':
        'http://localhost:7002/realms/m8flow/login-actions/restart',
    });

    expect(restartHiddenUsernameLogin(null, { replace: vi.fn() }, storage)).toBe(false);
    expect(storage.getItem('m8flow-hidden-username-login-restart-url')).toBeNull();
  });

  it('lets the manual fallback button clear the retry guard and restart the full sign-in flow', () => {
    const restartUrl = 'http://localhost:7002/realms/m8flow/login-actions/restart';
    const button = {
      getAttribute: vi.fn((attribute: string) => {
        if (attribute === 'data-login-restart-url') {
          return restartUrl;
        }
        return null;
      }),
    };
    const locationObject = { replace: vi.fn() };
    const storage = createStorage({
      'm8flow-hidden-username-login-restart-url': JSON.stringify({
        restartUrl,
        attempts: 2,
      }),
    });

    expect(
      handleManualHiddenUsernameRestart(button as unknown as Element, locationObject, storage),
    ).toBe(true);
    expect(storage.getItem('m8flow-hidden-username-login-restart-url')).toBeNull();
    expect(locationObject.replace).toHaveBeenCalledWith(restartUrl);
  });
});

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import {
  handleManualHiddenUsernameRestart,
  restartHiddenUsernameLogin,
} from '../../../m8flow-backend/keycloak/themes/m8flow/login/resources/js/restartHiddenUsernameLogin.js';

// Resolved from the Vitest root (m8flow-frontend), matching how the theme JS above is
// imported across the repo boundary.
const LOGIN_USERNAME_TEMPLATE = readFileSync(
  resolve(
    process.cwd(),
    '../m8flow-backend/keycloak/themes/m8flow/login/login-username.ftl',
  ),
  'utf8',
);

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

  it('leaves the manual fallback hidden while auto-restart attempts remain', () => {
    document.body.innerHTML =
      '<div id="m8f-hidden-username-login-fallback" hidden></div>';
    const marker = {
      getAttribute: vi.fn((attribute: string) => {
        if (attribute === 'data-login-restart-url') {
          return 'http://localhost:7002/realms/m8flow/login-actions/restart';
        }
        if (attribute === 'data-login-restart-fallback-id') {
          return 'm8f-hidden-username-login-fallback';
        }
        return null;
      }),
    };
    const fallback = document.getElementById('m8f-hidden-username-login-fallback') as HTMLDivElement;

    expect(restartHiddenUsernameLogin(marker as unknown as Element, { replace: vi.fn() }, createStorage())).toBe(true);
    expect(fallback.hidden).toBe(true);
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

describe('login-username.ftl theme template', () => {
  // The fixtures above render the fallback with `hidden`, so they cannot catch the template
  // shipping it visible. It did: the "sign-in form did not fully load" message then painted
  // on every username-only render and showFallback()'s `fallback.hidden = false` was a no-op.
  it('renders the manual fallback hidden so it only appears once showFallback runs', () => {
    const openingTag = LOGIN_USERNAME_TEMPLATE.match(
      /<div\b[^>]*\bid="m8f-hidden-username-login-fallback"[^>]*>/,
    );

    expect(openingTag).not.toBeNull();
    // Standalone `hidden` attribute only -- `\bhidden\b` would also match inside the
    // element's own id/class, which would make this assertion vacuous.
    expect(openingTag?.[0]).toMatch(/\shidden(?=[\s>])/);
  });

  it('keeps a non-module reveal guard for when the ES module cannot load', () => {
    expect(LOGIN_USERNAME_TEMPLATE).toContain('fallback.hidden = false;');
  });
});

import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';

import { isNetworkFailure, NetworkError, toNetworkError } from './networkErrors';

describe('network error classification', () => {
  it('uses the current locale when an existing error is displayed', async () => {
    const error = new NetworkError();
    const english = error.message;
    await i18n.changeLanguage('es');
    expect(error.message).toBe(i18n.t('shell.network.unableToConnect'));
    expect(error.message).not.toBe(english);
    expect(isNetworkFailure(error)).toBe(true);
  });
  it.each(['Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.'])(
    'normalizes the browser fetch failure %s and retains its cause', (message) => {
      const cause = new TypeError(message);
      expect(() => toNetworkError(cause)).toThrow(NetworkError);
      try {
        toNetworkError(cause);
      } catch (error) {
        expect(error).toBeInstanceOf(NetworkError);
        expect((error as NetworkError).cause).toBe(cause);
        expect(isNetworkFailure(error)).toBe(true);
      }
    },
  );

  it.each([
    'Failed to fetch dynamically imported module: https://example.com/assets/page.js',
    'error loading dynamically imported module: https://example.com/assets/page.js',
    'Importing a module script failed.',
    'Unable to preload CSS for /assets/page.css',
  ])('recognizes the page download failure %s', (message) => {
    expect(isNetworkFailure(new Error(message))).toBe(true);
  });

  it.each([
    new TypeError('Invalid URL'),
    new TypeError('Request with GET/HEAD method cannot have body.'),
    new TypeError('Cannot read properties of undefined'),
    new Error('Failed to fetch'),
    new Error('Syntax error in dynamically imported module'),
    new DOMException('The operation was aborted.', 'AbortError'),
    null,
  ])('passes unrelated failures through unchanged: %s', (error) => {
    expect(isNetworkFailure(error)).toBe(false);
    expect(() => toNetworkError(error)).toThrow();
    try { toNetworkError(error); } catch (caught) { expect(caught).toBe(error); }
  });
});

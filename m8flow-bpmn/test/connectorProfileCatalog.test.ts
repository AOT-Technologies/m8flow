import { describe, expect, it, vi } from 'vitest';

import { createConnectorProfileCatalog } from '../lib/features/connectorProfileCatalog';

describe('createConnectorProfileCatalog', () => {
  it('starts idle per connector type', () => {
    const catalog = createConnectorProfileCatalog();
    expect(catalog.getState('http')).toEqual({ status: 'idle' });
  });

  it('markLoading transitions idle → loading once per type', () => {
    const catalog = createConnectorProfileCatalog();
    expect(catalog.markLoading('http')).toBe(true);
    expect(catalog.getState('http')).toEqual({ status: 'loading' });
    expect(catalog.markLoading('http')).toBe(false);
    expect(catalog.markLoading('smtp')).toBe(true);
  });

  it('caches an empty active-profile list as loaded', () => {
    const catalog = createConnectorProfileCatalog();
    catalog.markLoading('http');
    catalog.setLoaded('http', {
      profiles: [],
      hiddenFieldIds: ['basic_auth_username', 'basic_auth_password'],
      supportsProfiles: true,
    });
    expect(catalog.getState('http')).toEqual({
      status: 'loaded',
      entry: {
        profiles: [],
        hiddenFieldIds: ['basic_auth_username', 'basic_auth_password'],
        supportsProfiles: true,
      },
    });
    expect(catalog.markLoading('http')).toBe(false);
  });

  it('keeps profile names and display names', () => {
    const catalog = createConnectorProfileCatalog();
    catalog.setLoaded('http', {
      profiles: [{ profile_name: 'http-prod', display_name: 'HTTP prod' }],
      hiddenFieldIds: ['basic_auth_username'],
      supportsProfiles: true,
    });
    const state = catalog.getState('http');
    expect(state.status === 'loaded' && state.entry.profiles).toEqual([
      { profile_name: 'http-prod', display_name: 'HTTP prod' },
    ]);
  });

  it('reset returns every type to idle', () => {
    const catalog = createConnectorProfileCatalog();
    catalog.setLoaded('http', { profiles: [], supportsProfiles: true });
    catalog.reset();
    expect(catalog.getState('http')).toEqual({ status: 'idle' });
    expect(catalog.markLoading('http')).toBe(true);
  });

  it('notifies subscribers on load and stops after unsubscribe', () => {
    const catalog = createConnectorProfileCatalog();
    const listener = vi.fn();
    const unsubscribe = catalog.subscribe(listener);
    catalog.setLoaded('http', { profiles: [], supportsProfiles: true });
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    catalog.setLoaded('http', { profiles: [{ profile_name: 'a', display_name: 'A' }] });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

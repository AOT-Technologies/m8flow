import { describe, expect, it, vi } from 'vitest';

import {
  catalogHasOperators,
  createServiceTaskOperatorCatalog,
} from '../lib/features/serviceTaskOperatorCatalog';

const HTTP_GET = {
  id: 'http/GetRequestV2',
  parameters: [
    { id: 'url', type: 'str' },
    { id: 'headers', type: 'any' },
    { id: 'params', type: 'any' },
    { id: 'basic_auth_username', type: 'str' },
    { id: 'basic_auth_password', type: 'str' },
    { id: 'attempts', type: 'int' },
  ],
};

describe('createServiceTaskOperatorCatalog', () => {
  it('starts idle with no operators to mount', () => {
    const catalog = createServiceTaskOperatorCatalog();
    expect(catalog.getState()).toEqual({ status: 'idle' });
    expect(catalogHasOperators(catalog.getState())).toBe(false);
  });

  it('markLoading transitions idle → loading once and refuses a second request', () => {
    const catalog = createServiceTaskOperatorCatalog();
    expect(catalog.markLoading()).toBe(true);
    expect(catalog.getState()).toEqual({ status: 'loading' });
    expect(catalog.markLoading()).toBe(false);
  });

  it('caches an empty catalog as loaded so the Action tab can skip the vendor select', () => {
    const catalog = createServiceTaskOperatorCatalog();
    catalog.markLoading();
    catalog.setLoaded([]);
    expect(catalog.getState()).toEqual({ status: 'loaded', operators: [] });
    expect(catalogHasOperators(catalog.getState())).toBe(false);
  });

  it('caches HTTP V2 operators including their parameter lists', () => {
    const catalog = createServiceTaskOperatorCatalog();
    catalog.setLoaded([HTTP_GET]);
    expect(catalogHasOperators(catalog.getState())).toBe(true);
    expect(catalog.getState()).toEqual({ status: 'loaded', operators: [HTTP_GET] });
  });

  it('treats a missing parameters array as empty rather than undefined', () => {
    const catalog = createServiceTaskOperatorCatalog();
    catalog.setLoaded([{ id: 'http/PostRequestV2', parameters: undefined as unknown as [] }]);
    expect(catalog.getState()).toEqual({
      status: 'loaded',
      operators: [{ id: 'http/PostRequestV2', parameters: [] }],
    });
  });

  it('does not re-request after an empty catalog is loaded', () => {
    const catalog = createServiceTaskOperatorCatalog();
    catalog.markLoading();
    catalog.setLoaded([]);
    expect(catalog.markLoading()).toBe(false);
  });

  it('notifies subscribers on load and stops after unsubscribe', () => {
    const catalog = createServiceTaskOperatorCatalog();
    const listener = vi.fn();
    const unsubscribe = catalog.subscribe(listener);
    catalog.setLoaded([]);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    catalog.setLoaded([HTTP_GET]);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('reset returns the store to idle so a later session can request again', () => {
    const catalog = createServiceTaskOperatorCatalog();
    catalog.setLoaded([]);
    catalog.reset();
    expect(catalog.getState()).toEqual({ status: 'idle' });
    expect(catalog.markLoading()).toBe(true);
  });
});

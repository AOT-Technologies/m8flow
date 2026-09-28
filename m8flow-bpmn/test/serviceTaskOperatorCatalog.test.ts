import { describe, expect, it, vi } from 'vitest';

import {
  catalogHasOperators,
  createServiceTaskOperatorCatalog,
  groupOperatorsByConnector,
  operatorActionLabel,
  writeServiceTaskOperator,
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

describe('groupOperatorsByConnector', () => {
  it('groups by catalog connectorId/name in order and labels actions', () => {
    const groups = groupOperatorsByConnector([
      { id: 'http/GetRequestV2', parameters: [], connectorId: 'http', connectorName: 'HTTP', name: 'GetRequestV2' },
      { id: 'github/ListPullRequests', parameters: [] },
      { id: 'http/PostRequestV2', parameters: [], connectorId: 'http', connectorName: 'HTTP' },
    ]);
    expect(groups.map((g) => [g.id, g.name, g.operators.map(operatorActionLabel)])).toEqual([
      ['http', 'HTTP', ['GetRequestV2', 'PostRequestV2']],
      ['github', 'github', ['ListPullRequests']],
    ]);
  });

  it('keeps optional labels through normalize', () => {
    const catalog = createServiceTaskOperatorCatalog();
    catalog.setLoaded([{ ...HTTP_GET, connectorId: 'http', connectorName: 'HTTP', name: 'GetRequestV2' }]);
    const state = catalog.getState();
    expect(state.status === 'loaded' && state.operators[0]).toMatchObject({ connectorName: 'HTTP', name: 'GetRequestV2' });
  });
});

describe('writeServiceTaskOperator', () => {
  // Minimal moddle stand-in: plain objects with $type, extensionElements.get('values').
  const moddle = {
    create(type: string) {
      const obj: any = { $type: type };
      if (type === 'bpmn:ExtensionElements') {
        obj.values = [];
        obj.get = (key: string) => obj[key];
      }
      return obj;
    },
  };
  const POST = { id: 'http/PostRequestV2', parameters: [{ id: 'url', type: 'str' }, { id: 'data', type: 'any' }] };
  const operatorOf = (bo: any) => bo.extensionElements.values.find((v: any) => v.$type === 'spiffworkflow:ServiceTaskOperator');

  it('creates the operator element with one parameter per catalog param', () => {
    const bo: any = { id: 'Task_1' };
    writeServiceTaskOperator(bo, moddle, HTTP_GET, {});
    const op = operatorOf(bo);
    expect(op.id).toBe('http/GetRequestV2');
    expect(op.parameterList.parameters.map((p: any) => [p.$type, p.id, p.type])).toEqual(
      HTTP_GET.parameters.map((p) => ['spiffworkflow:Parameter', p.id, p.type]),
    );
    expect(bo.extensionElements.values.filter((v: any) => v.$type === 'spiffworkflow:ServiceTaskOperator')).toHaveLength(1);
  });

  it('keeps other extension elements and restores values when switching A → B → A', () => {
    const bo: any = { id: 'Task_1' };
    const memory = {};
    writeServiceTaskOperator(bo, moddle, HTTP_GET, memory);
    bo.extensionElements.values.push({ $type: 'spiffworkflow:Other' });
    operatorOf(bo).parameterList.parameters[0].value = '"https://x"';
    writeServiceTaskOperator(bo, moddle, POST, memory);
    expect(operatorOf(bo).id).toBe('http/PostRequestV2');
    writeServiceTaskOperator(bo, moddle, HTTP_GET, memory);
    expect(operatorOf(bo).parameterList.parameters[0].value).toBe('"https://x"');
    expect(bo.extensionElements.values.some((v: any) => v.$type === 'spiffworkflow:Other')).toBe(true);
  });
});

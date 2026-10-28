import { describe, expect, it, vi } from 'vitest';

import { decisionTableI18nModule, expressionViewI18nModule } from '../lib/features/dmnViewI18n';

function eventBusStub() {
  const handlers = new Map<string, Array<() => void>>();
  return {
    on: (event: string, handler: () => void) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
    fire: vi.fn(),
    emit: (event: string) => (handlers.get(event) ?? []).forEach((handler) => handler()),
  };
}

describe('decisionTableI18nModule', () => {
  it('re-renders the table in place and re-translates the CSS header placeholders', () => {
    const eventBus = eventBusStub();
    const container = document.createElement('div');
    let dictionary: Record<string, string> = { Input: 'Entrada', Output: 'Saída' };
    const DecisionTableI18n = decisionTableI18nModule.m8flowDecisionTableI18n[1] as any;
    const services: Record<string, any> = {
      throttle: (fn: any) => fn,
      sheet: { getRoot: () => ({ id: 'DT_1', rows: [], cols: [] }) },
      components: { getComponents: () => [], getComponent: () => null },
      eventBus,
      changeSupport: { onElementsChanged: vi.fn(), offElementsChanged: vi.fn() },
    };
    const injector = {
      get: vi.fn((name: string) => services[name]),
    };

    new DecisionTableI18n(
      eventBus,
      { getContainer: () => container },
      injector,
      (template: string) => dictionary[template] ?? template,
    );

    expect(container.style.getPropertyValue('--m8flow-dmn-input-placeholder')).toBe('"Entrada"');
    expect(container.style.getPropertyValue('--m8flow-dmn-output-placeholder')).toBe('"Saída"');

    dictionary = { Input: '输入', Output: '输出' };
    eventBus.emit('i18n.changed');

    expect(container.style.getPropertyValue('--m8flow-dmn-input-placeholder')).toBe('"输入"');
  });
});

describe('expressionViewI18nModule', () => {
  it('re-mounts the literal / boxed expression view on a language switch', () => {
    const eventBus = eventBusStub();
    const ExpressionViewI18n = expressionViewI18nModule.m8flowExpressionViewI18n[1] as any;

    new ExpressionViewI18n(eventBus);
    eventBus.emit('i18n.changed');

    expect(eventBus.fire).toHaveBeenCalledWith('renderer.mount');
  });
});

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
  function mount(root: unknown) {
    const eventBus = eventBusStub();
    const container = document.createElement('div');
    const state = { dictionary: { Input: 'Entrada', Output: 'Saída' } as Record<string, string> };
    const DecisionTableI18n = decisionTableI18nModule.m8flowDecisionTableI18n[1] as any;
    new DecisionTableI18n(
      eventBus,
      { getRoot: () => root },
      { getContainer: () => container },
      (template: string) => state.dictionary[template] ?? template,
    );
    const placeholders = () => [
      container.style.getPropertyValue('--m8flow-dmn-input-placeholder'),
      container.style.getPropertyValue('--m8flow-dmn-output-placeholder'),
    ];
    return { eventBus, state, placeholders };
  }

  it('re-renders the table in place and re-translates the CSS header placeholders on every switch', () => {
    const root = { id: 'DT_1' };
    const { eventBus, state, placeholders } = mount(root);
    expect(placeholders()).toEqual(['"Entrada"', '"Saída"']);

    state.dictionary = { Input: '输入', Output: '输出' };
    eventBus.emit('i18n.changed');
    expect(placeholders()).toEqual(['"输入"', '"输出"']);

    state.dictionary = { Input: 'Eingabe', Output: 'Ausgabe' };
    eventBus.emit('i18n.changed');
    expect(placeholders()).toEqual(['"Eingabe"', '"Ausgabe"']);

    // TableComponent force-updates on its root: no re-import, so the command stack is untouched.
    expect(eventBus.fire).toHaveBeenCalledTimes(2);
    expect(eventBus.fire).toHaveBeenNthCalledWith(2, 'elements.changed', { elements: [root] });
  });

  it('refreshes the placeholders when the table is opened again after a switch', () => {
    const { eventBus, state, placeholders } = mount({ id: 'DT_1' });

    state.dictionary = { Input: '输入', Output: '输出' };
    eventBus.emit('root.added');

    expect(placeholders()).toEqual(['"输入"', '"输出"']);
  });

  it('does not fire elements.changed before a table is open', () => {
    const { eventBus } = mount(undefined);

    eventBus.emit('i18n.changed');

    expect(eventBus.fire).not.toHaveBeenCalled();
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

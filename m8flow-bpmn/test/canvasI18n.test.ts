import { describe, expect, it, vi } from 'vitest';

import { canvasI18nModule } from '../lib/features/canvasI18n';

function mount(translate: (template: string) => string) {
  const handlers = new Map<string, Array<(event?: any) => void>>();
  const eventBus = {
    on: (event: string, handler: (event?: any) => void) => handlers.set(event, [...(handlers.get(event) ?? []), handler]),
  };
  const providers: Array<{ priority: number; provider: any }> = [];
  const palette = { registerProvider: (priority: number, provider: any) => providers.push({ priority, provider }) };
  const contextPad = { isOpen: vi.fn(() => true), open: vi.fn() };
  const CanvasI18n = canvasI18nModule.m8flowCanvasI18n[1] as any;
  new CanvasI18n(eventBus, palette, contextPad, translate);
  const fire = (event: string, payload?: unknown) => (handlers.get(event) ?? []).forEach((handler) => handler(payload));
  return { providers, contextPad, fire };
}

describe('canvasI18nModule', () => {
  it('translates palette titles last, including ones a provider left raw', () => {
    const { providers } = mount((template) => ({ 'Create DataInput': '创建数据输入' })[template] ?? template);
    const [{ priority, provider }] = providers;
    const entries = { 'create.data-input': { title: 'Create DataInput' }, separator: { separator: true } };

    expect(priority).toBe(1);
    expect(provider.getPaletteEntries()(entries)).toEqual({
      'create.data-input': { title: '创建数据输入' },
      separator: { separator: true },
    });
  });

  it('rebuilds an open context pad when the language changes', () => {
    const { contextPad, fire } = mount((template) => template);
    const target = { id: 'Task_1' };

    fire('i18n.changed');
    expect(contextPad.open).not.toHaveBeenCalled();

    fire('contextPad.open', { current: { target } });
    fire('i18n.changed');
    expect(contextPad.open).toHaveBeenCalledWith(target, true);

    contextPad.open.mockClear();
    fire('contextPad.close');
    fire('i18n.changed');
    expect(contextPad.open).not.toHaveBeenCalled();
  });
});

import { describe, expect, it } from 'vitest';

import { PaletteMinimize, paletteMinimizeModule } from '../lib/features/paletteMinimize';

// diagram-js's palette markup, with its open / close / toggle behaviour.
function mountPalette(translate: (template: string) => string = (template) => template) {
  const container = document.createElement('div');
  container.className = 'djs-palette open';
  container.innerHTML = '<div class="djs-palette-entries"></div><div class="djs-palette-toggle"></div>';
  const palette = {
    isOpen: () => container.classList.contains('open'),
    open: () => container.classList.add('open'),
    close: () => container.classList.remove('open'),
  };
  container.querySelector('.djs-palette-toggle')!.addEventListener('click', () => palette.open());

  const handlers = new Map<string, Array<(event?: unknown) => void>>();
  const eventBus = {
    on: (event: string, priorityOrHandler: unknown, handler?: (event?: unknown) => void) => {
      const callback = (handler ?? priorityOrHandler) as (event?: unknown) => void;
      handlers.set(event, [...(handlers.get(event) ?? []), callback]);
    },
  };
  new (PaletteMinimize as unknown as new (...args: unknown[]) => void)(eventBus, palette, translate);
  const fire = (event: string, payload?: unknown) => (handlers.get(event) ?? []).forEach((handler) => handler(payload));
  fire('palette.create', { container });
  return { container, palette, fire };
}

describe('paletteMinimizeModule', () => {
  it('registers as a DI type', () => {
    expect(paletteMinimizeModule.__init__).toEqual(['m8flowPaletteMinimize']);
  });

  it('starts open, minimizes from its button and reopens from the toggle', () => {
    const { container, palette } = mountPalette();
    const minimize = container.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement;
    const toggle = container.querySelector('.djs-palette-toggle') as HTMLElement;

    expect(palette.isOpen()).toBe(true);
    expect(minimize.title).toBe('Minimize');
    expect(toggle.title).toBe('Expand');

    minimize.click();
    expect(palette.isOpen()).toBe(false);

    toggle.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    expect(palette.isOpen()).toBe(true);
  });

  it('keeps a minimized palette minimized when a language switch re-renders it', () => {
    let dictionary: Record<string, string> = {};
    const { container, palette, fire } = mountPalette((template) => dictionary[template] ?? template);
    (container.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement).click();

    // diagram-js's own i18n.changed handler reopens the palette first.
    palette.open();
    dictionary = { Expand: 'Erweitern' };
    fire('i18n.changed');
    expect(palette.isOpen()).toBe(false);
    expect((container.querySelector('.djs-palette-toggle') as HTMLElement).title).toBe('Erweitern');

    (container.querySelector('.djs-palette-toggle') as HTMLElement).click();
    palette.open();
    fire('i18n.changed');
    expect(palette.isOpen()).toBe(true);
  });
});

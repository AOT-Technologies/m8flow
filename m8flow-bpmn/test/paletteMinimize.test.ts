import { describe, expect, it } from 'vitest';

import { PaletteMinimize, paletteMinimizeModule } from '../lib/features/paletteMinimize';

// diagram-js's palette markup, with its open / close / toggle behaviour.
function mountPalette(translate: (template: string) => string = (template) => template, toggleTag = 'div') {
  const container = document.createElement('div');
  container.className = 'djs-palette open';
  const entries = document.createElement('div');
  entries.className = 'djs-palette-entries';
  const toggleElement = document.createElement(toggleTag);
  toggleElement.className = 'djs-palette-toggle';
  container.append(entries, toggleElement);
  // Like diagram-js, open / close fire palette.changed.
  let notify: (open: boolean) => void = () => {};
  const palette = {
    isOpen: () => container.classList.contains('open'),
    open: () => {
      container.classList.add('open');
      notify(true);
    },
    close: () => {
      container.classList.remove('open');
      notify(false);
    },
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
  notify = (open) => fire('palette.changed', { open });
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

  it('minimizes in expanded view and restores the previous state on exit', () => {
    const { container, palette, fire } = mountPalette();
    const toggle = container.querySelector('.djs-palette-toggle') as HTMLElement;

    fire('m8flow.expand.changed', { expanded: true });
    expect(palette.isOpen()).toBe(false);
    toggle.click();
    expect(palette.isOpen()).toBe(true);
    fire('m8flow.expand.changed', { expanded: false });
    expect(palette.isOpen()).toBe(true);

    // Minimized before expanding stays minimized after leaving.
    (container.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement).click();
    fire('m8flow.expand.changed', { expanded: true });
    fire('m8flow.expand.changed', { expanded: false });
    expect(palette.isOpen()).toBe(false);
  });

  it('on leaving expanded view restores the state from before expanding, not changes made while expanded', () => {
    // Open before expanding; reopened then minimized again while expanded.
    const first = mountPalette();
    first.fire('m8flow.expand.changed', { expanded: true });
    (first.container.querySelector('.djs-palette-toggle') as HTMLElement).click();
    (first.container.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement).click();
    first.fire('m8flow.expand.changed', { expanded: false });
    expect(first.palette.isOpen()).toBe(true);

    // Minimized before expanding; reopened while expanded.
    const second = mountPalette();
    (second.container.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement).click();
    second.fire('m8flow.expand.changed', { expanded: true });
    (second.container.querySelector('.djs-palette-toggle') as HTMLElement).click();
    expect(second.palette.isOpen()).toBe(true);
    second.fire('m8flow.expand.changed', { expanded: false });
    expect(second.palette.isOpen()).toBe(false);
  });

  it('names its icon-only controls with aria-label and translates it', () => {
    let dictionary: Record<string, string> = {};
    const { container, fire } = mountPalette((template) => dictionary[template] ?? template);
    const minimize = container.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement;
    const toggle = container.querySelector('.djs-palette-toggle') as HTMLElement;
    expect([minimize.getAttribute('aria-label'), toggle.getAttribute('aria-label')]).toEqual(['Minimize', 'Expand']);
    dictionary = { Minimize: 'Minimieren', Expand: 'Erweitern' };
    fire('i18n.changed');
    expect([minimize.getAttribute('aria-label'), toggle.getAttribute('aria-label')]).toEqual(['Minimieren', 'Erweitern']);
  });

  it('keeps aria-expanded on both controls in step with the palette', () => {
    const { container, palette, fire } = mountPalette();
    const minimize = container.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement;
    const toggle = container.querySelector('.djs-palette-toggle') as HTMLElement;
    const states = () => [minimize.getAttribute('aria-expanded'), toggle.getAttribute('aria-expanded')];

    expect(states()).toEqual(['true', 'true']);
    minimize.click();
    expect(states()).toEqual(['false', 'false']);
    toggle.click();
    expect(states()).toEqual(['true', 'true']);

    fire('m8flow.expand.changed', { expanded: true });
    expect(states()).toEqual(['false', 'false']);
    fire('m8flow.expand.changed', { expanded: false });
    expect(states()).toEqual(['true', 'true']);
    expect(palette.isOpen()).toBe(true);
  });

  it('gives a <div> toggle a button role and keyboard access, and leaves a native <button> alone', () => {
    const { container: divPalette } = mountPalette();
    const divToggle = divPalette.querySelector('.djs-palette-toggle') as HTMLElement;
    expect(divToggle.getAttribute('role')).toBe('button');
    expect(divToggle.tabIndex).toBe(0);

    const { container: buttonPalette, palette } = mountPalette(undefined, 'button');
    const buttonToggle = buttonPalette.querySelector('.djs-palette-toggle') as HTMLButtonElement;
    expect(buttonToggle.hasAttribute('role')).toBe(false);
    expect(buttonToggle.hasAttribute('tabindex')).toBe(false);
    // Still reopens a minimized palette and keeps its tooltip / state.
    (buttonPalette.querySelector('.m8flow-bpmn-palette-minimize') as HTMLButtonElement).click();
    buttonToggle.click();
    expect(palette.isOpen()).toBe(true);
    expect(buttonToggle.title).toBe('Expand');
    expect(buttonToggle.getAttribute('aria-expanded')).toBe('true');
  });

  it('builds its chevron as an SVG element, not a markup string', () => {
    const { container } = mountPalette();
    const svg = container.querySelector('.m8flow-bpmn-palette-minimize svg') as SVGSVGElement;
    expect(svg.namespaceURI).toBe('http://www.w3.org/2000/svg');
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

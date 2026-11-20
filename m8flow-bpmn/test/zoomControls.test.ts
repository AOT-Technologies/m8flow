import { describe, expect, it, vi } from 'vitest';

import { fillViewbox, ZoomControls, zoomControlsModule } from '../lib/features/zoomControls';

function mountZoomControls(translate: (template: string) => string = (template) => template) {
  const parent = document.createElement('div');
  const zoom = vi.fn((level?: unknown) => (typeof level === 'number' ? level : 1));
  const resized = vi.fn();
  // A wide process: 5000 x 1000 diagram in a 1000 x 600 canvas.
  const viewbox = vi.fn((box?: unknown) => box ?? { outer: { width: 1000, height: 600 }, inner: { x: 0, y: 0, width: 5000, height: 1000 } });
  const canvas = { getContainer: () => parent, zoom, resized, viewbox };
  const handlers = new Map<string, Array<() => void>>();
  const eventBus = {
    on: (event: string, handler: () => void) => {
      handlers.set(event, [...(handlers.get(event) ?? []), handler]);
    },
    fire: vi.fn(),
  };
  new (ZoomControls as unknown as new (c: unknown, e: unknown, t: unknown) => void)(canvas, eventBus, translate);
  const fire = (event: string) => (handlers.get(event) ?? []).forEach((handler) => handler());
  return { parent, zoom, resized, viewbox, fire, busFire: eventBus.fire };
}

describe('zoomControlsModule', () => {
  it('registers the same DI factory BPMN and DMN DRD both load', () => {
    expect(zoomControlsModule.__init__).toEqual(['m8flowZoomControls']);
    expect(zoomControlsModule.m8flowZoomControls[0]).toBe('type');
  });

  it('appends in / out / fit buttons and calls canvas.zoom', () => {
    const { parent, zoom } = mountZoomControls();

    expect(parent.classList.contains('m8flow-bpmn')).toBe(true);
    const zoomIn = parent.querySelector('[title="Zoom in"]') as HTMLButtonElement;
    const zoomOut = parent.querySelector('[title="Zoom out"]') as HTMLButtonElement;
    const fit = parent.querySelector('[title="Fit to viewport"]') as HTMLButtonElement;
    expect(zoomIn).toBeTruthy();
    expect(zoomOut).toBeTruthy();
    expect(fit).toBeTruthy();

    zoomIn.click();
    expect(zoom).toHaveBeenCalledWith(1.1);
    zoomOut.click();
    expect(zoom).toHaveBeenCalledWith(0.9);
    fit.click();
    expect(zoom).toHaveBeenCalledWith('fit-viewport', 'auto');
  });

  it('expands the host expand-root over the viewport and collapses on Escape', () => {
    const host = document.createElement('div');
    host.setAttribute('data-m8flow-expand-root', '');
    document.body.appendChild(host);
    const { parent, zoom, resized, viewbox, fire, busFire } = mountZoomControls();
    host.appendChild(parent);
    const expand = parent.querySelector('[data-zoom="expand"]') as HTMLButtonElement;

    (expand.querySelector('svg') as SVGElement).dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(host.classList.contains('m8flow-bpmn--expanded')).toBe(true);
    expect(parent.classList.contains('m8flow-bpmn--expanded')).toBe(false);
    expect(expand.getAttribute('aria-pressed')).toBe('true');
    expect(expand.title).toBe('Exit expanded view');
    expect(resized).toHaveBeenCalled();
    // Expanded fills the screen height rather than fitting the whole width.
    expect(viewbox).toHaveBeenLastCalledWith(expect.objectContaining({ width: 1000 / 0.48 }));
    expect(zoom).not.toHaveBeenCalledWith('fit-viewport', 'auto');
    expect(busFire).toHaveBeenLastCalledWith('m8flow.expand.changed', { expanded: true });

    // Escape from outside the diagram (an open dialog) leaves it expanded.
    const dialog = document.createElement('div');
    document.body.appendChild(dialog);
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(host.classList.contains('m8flow-bpmn--expanded')).toBe(true);

    expand.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(host.classList.contains('m8flow-bpmn--expanded')).toBe(false);
    expect(expand.title).toBe('Expand view');
    expect(busFire).toHaveBeenLastCalledWith('m8flow.expand.changed', { expanded: false });
    expect(zoom).toHaveBeenLastCalledWith('fit-viewport', 'auto');

    expand.click();
    fire('diagram.destroy');
    expect(host.classList.contains('m8flow-bpmn--expanded')).toBe(false);
    host.remove();
    dialog.remove();
  });

  it('mounts in config.zoomControls.parent when the host gives one', () => {
    const parent = document.createElement('div');
    const slot = document.createElement('div');
    const canvas = { getContainer: () => parent, zoom: vi.fn(), resized: vi.fn() };
    const eventBus = { on: vi.fn() };
    new (ZoomControls as unknown as new (...args: unknown[]) => void)(canvas, eventBus, (t: string) => t, { parent: slot });

    expect(parent.querySelector('.m8flow-bpmn-zoom')).toBeNull();
    expect(slot.querySelector('.m8flow-bpmn-zoom.m8flow-bpmn-zoom--inline')).toBeTruthy();
    expect((ZoomControls as unknown as { $inject: string[] }).$inject).toContain('config.zoomControls');
  });

  it('fillViewbox fills the height of a wide diagram and starts at its left edge', () => {
    const pad = { top: 80, right: 40, bottom: 40, left: 120 };
    // 840 x 480 available; height wins: scale 0.48, wider than the screen.
    const box = fillViewbox({ width: 1000, height: 600 }, { x: 100, y: 50, width: 5000, height: 1000 }, pad);
    const scale = 1000 / box.width;
    expect(scale).toBeCloseTo(0.48);
    expect((100 - box.x) * scale).toBeCloseTo(pad.left);
    expect((50 - box.y) * scale).toBeCloseTo(pad.top);
  });

  it('fillViewbox never zooms past 100% and centres a small diagram', () => {
    const box = fillViewbox({ width: 1000, height: 600 }, { x: 0, y: 0, width: 200, height: 100 });
    expect(box.width).toBe(1000);
    expect(-box.x).toBeCloseTo(120 + (840 - 200) / 2);
    expect(-box.y).toBeCloseTo(80 + (480 - 100) / 2);
  });

  it('keeps the view expanded when Escape is pressed in a form field inside it', () => {
    const host = document.createElement('div');
    host.setAttribute('data-m8flow-expand-root', '');
    document.body.appendChild(host);
    const { parent, fire } = mountZoomControls();
    host.appendChild(parent);
    (parent.querySelector('[data-zoom="expand"]') as HTMLButtonElement).click();

    for (const tag of ['input', 'textarea', 'select']) {
      const field = document.createElement(tag);
      host.appendChild(field);
      field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      expect(host.classList.contains('m8flow-bpmn--expanded')).toBe(true);
    }

    fire('diagram.destroy');
    host.remove();
  });

  it('fillViewbox returns a finite viewbox for empty or negative sizes', () => {
    const cases = [
      { outer: { width: 1000, height: 600 }, inner: { x: 0, y: 0, width: 0, height: 100 } },
      { outer: { width: 1000, height: 600 }, inner: { x: 0, y: 0, width: 100, height: 0 } },
      { outer: { width: 1000, height: 600 }, inner: { x: 10, y: 10, width: -50, height: -20 } },
      { outer: { width: 0, height: 0 }, inner: { x: 0, y: 0, width: 5000, height: 1000 } },
    ];
    for (const { outer, inner } of cases) {
      const box = fillViewbox(outer, inner);
      expect(Object.values(box).every(Number.isFinite)).toBe(true);
      expect(box.width).toBeGreaterThan(0);
      expect(box.height).toBeGreaterThan(0);
    }
  });

  it('clears the expanded class from the element it was added to, even after re-parenting', () => {
    const host = document.createElement('div');
    host.setAttribute('data-m8flow-expand-root', '');
    const other = document.createElement('div');
    document.body.append(host, other);
    const { parent, fire } = mountZoomControls();
    host.appendChild(parent);
    const expand = parent.querySelector('[data-zoom="expand"]') as HTMLButtonElement;

    expand.click();
    expect(host.classList.contains('m8flow-bpmn--expanded')).toBe(true);
    // The host moves the canvas out of the expand root while expanded.
    other.appendChild(parent);
    fire('diagram.destroy');
    expect(host.classList.contains('m8flow-bpmn--expanded')).toBe(false);
    expect(parent.classList.contains('m8flow-bpmn--expanded')).toBe(false);

    host.remove();
    other.remove();
  });

  it('builds its icons as SVG elements, not markup strings', () => {
    const { parent } = mountZoomControls();
    const expand = parent.querySelector('[data-zoom="expand"]') as HTMLButtonElement;
    const svg = expand.querySelector('svg') as SVGSVGElement;
    expect(svg.namespaceURI).toBe('http://www.w3.org/2000/svg');
    expect(svg.querySelectorAll('path')).toHaveLength(4);
  });

  it('falls back to the canvas when config.zoomControls.parent is not an element', () => {
    for (const bad of ['not-an-element', {}, 42]) {
      const parent = document.createElement('div');
      const canvas = { getContainer: () => parent, zoom: vi.fn(), resized: vi.fn() };
      expect(() =>
        new (ZoomControls as unknown as new (...args: unknown[]) => void)(canvas, { on: vi.fn() }, (t: string) => t, { parent: bad }),
      ).not.toThrow();
      const pill = parent.querySelector('.m8flow-bpmn-zoom') as HTMLElement;
      expect(pill).toBeTruthy();
      expect(pill.classList.contains('m8flow-bpmn-zoom--inline')).toBe(false);
    }

    // A detached element is still a valid slot.
    const detached = document.createElement('div');
    const parent = document.createElement('div');
    const canvas = { getContainer: () => parent, zoom: vi.fn(), resized: vi.fn() };
    new (ZoomControls as unknown as new (...args: unknown[]) => void)(canvas, { on: vi.fn() }, (t: string) => t, { parent: detached });
    expect(detached.querySelector('.m8flow-bpmn-zoom--inline')).toBeTruthy();
  });

  it('names the icon-only expand button with an aria-label that follows its state', () => {
    const { parent } = mountZoomControls();
    const expand = parent.querySelector('[data-zoom="expand"]') as HTMLButtonElement;
    expect(expand.getAttribute('aria-label')).toBe('Expand view');
    expand.click();
    expect(expand.getAttribute('aria-label')).toBe('Exit expanded view');
    expand.click();
    expect(expand.getAttribute('aria-label')).toBe('Expand view');
  });

  it('removes the chrome on diagram.destroy', () => {
    const { parent, fire } = mountZoomControls();
    expect(parent.querySelector('.m8flow-bpmn-zoom')).toBeTruthy();
    fire('diagram.destroy');
    expect(parent.querySelector('.m8flow-bpmn-zoom')).toBeNull();
  });

  it('translates button titles and re-translates on i18n.changed', () => {
    const dictionaries: Record<string, Record<string, string>> = {
      de: { 'Zoom in': 'Vergrößern', 'Zoom out': 'Verkleinern', 'Fit to viewport': 'An Ansicht anpassen' },
      es: { 'Zoom in': 'Acercar' },
    };
    let language = 'de';
    const { parent, fire } = mountZoomControls((template) => dictionaries[language][template] ?? template);
    const titles = () => Array.from(parent.querySelectorAll('button')).map((button) => button.title);

    expect(titles()).toEqual(['Vergrößern', 'Verkleinern', 'An Ansicht anpassen', 'Expand view']);

    language = 'es';
    fire('i18n.changed');
    expect(titles()).toEqual(['Acercar', 'Zoom out', 'Fit to viewport', 'Expand view']);
  });

  it('keeps one set of controls across repeated language switches', () => {
    let language = 'de';
    const dictionaries: Record<string, Record<string, string>> = { de: { 'Zoom in': 'Vergrößern' }, es: { 'Zoom in': 'Acercar' } };
    const { parent, fire } = mountZoomControls((template) => dictionaries[language][template] ?? template);

    for (const next of ['es', 'de', 'es']) {
      language = next;
      fire('i18n.changed');
    }

    expect(parent.querySelectorAll('.m8flow-bpmn-zoom')).toHaveLength(1);
    expect(parent.querySelectorAll('button')).toHaveLength(4);
    expect((parent.querySelector('[data-zoom="in"]') as HTMLButtonElement).title).toBe('Acercar');
  });

  it('safely handles unexpected or missing data-zoom attributes without calling translate', () => {
    const translate = vi.fn((key: string) => key);
    const { parent, fire } = mountZoomControls(translate);
    translate.mockClear();

    const zoomRoot = parent.querySelector('.m8flow-bpmn-zoom') as HTMLElement;
    const rogueButton = document.createElement('button');
    rogueButton.dataset.zoom = 'unknown-action';
    rogueButton.title = 'Original';
    zoomRoot.appendChild(rogueButton);

    const emptyButton = document.createElement('button');
    emptyButton.title = 'Keep';
    zoomRoot.appendChild(emptyButton);

    expect(() => fire('i18n.changed')).not.toThrow();
    expect(rogueButton.title).toBe('Original');
    expect(emptyButton.title).toBe('Keep');
    expect(translate).not.toHaveBeenCalledWith(undefined);
  });
});

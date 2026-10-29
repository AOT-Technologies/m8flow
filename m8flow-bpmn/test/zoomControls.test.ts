import { describe, expect, it, vi } from 'vitest';

import { ZoomControls, zoomControlsModule } from '../lib/features/zoomControls';

function mountZoomControls(translate: (template: string) => string = (template) => template) {
  const parent = document.createElement('div');
  const zoom = vi.fn((level?: unknown) => (typeof level === 'number' ? level : 1));
  const canvas = { getContainer: () => parent, zoom };
  const handlers = new Map<string, Array<() => void>>();
  const eventBus = {
    on: (event: string, handler: () => void) => {
      handlers.set(event, [...(handlers.get(event) ?? []), handler]);
    },
  };
  new (ZoomControls as unknown as new (c: unknown, e: unknown, t: unknown) => void)(canvas, eventBus, translate);
  const fire = (event: string) => (handlers.get(event) ?? []).forEach((handler) => handler());
  return { parent, zoom, fire };
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

    expect(titles()).toEqual(['Vergrößern', 'Verkleinern', 'An Ansicht anpassen']);

    language = 'es';
    fire('i18n.changed');
    expect(titles()).toEqual(['Acercar', 'Zoom out', 'Fit to viewport']);
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
    expect(parent.querySelectorAll('button')).toHaveLength(3);
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

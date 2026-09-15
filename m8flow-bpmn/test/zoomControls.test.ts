import { describe, expect, it, vi } from 'vitest';

import { ZoomControls, zoomControlsModule } from '../lib/features/zoomControls';

function mountZoomControls() {
  const parent = document.createElement('div');
  const zoom = vi.fn((level?: unknown) => (typeof level === 'number' ? level : 1));
  const canvas = { getContainer: () => parent, zoom };
  const destroyHandlers: Array<() => void> = [];
  const eventBus = {
    on: (event: string, handler: () => void) => {
      if (event === 'diagram.destroy') destroyHandlers.push(handler);
    },
  };
  new (ZoomControls as unknown as new (c: unknown, e: unknown) => void)(canvas, eventBus);
  return { parent, zoom, destroyHandlers };
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
    const { parent, destroyHandlers } = mountZoomControls();
    expect(parent.querySelector('.m8flow-bpmn-zoom')).toBeTruthy();
    destroyHandlers.forEach((handler) => handler());
    expect(parent.querySelector('.m8flow-bpmn-zoom')).toBeNull();
  });
});

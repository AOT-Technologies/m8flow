/**
 * DOM zoom chrome for diagram-js (no React). Same role as camunda minimap —
 * package-owned modeler/viewer chrome. Used on BPMN Modeler, NavigatedViewer,
 * and the DMN DRD viewer so fit + toolbar zoom match.
 */
import '../assets/zoom-controls.css';

export function ZoomControls(this: any, canvas: any, eventBus: any) {
  const parent = canvas.getContainer();
  parent.classList.add('m8flow-bpmn');

  const root = document.createElement('div');
  root.className = 'm8flow-bpmn-zoom';
  root.innerHTML = [
    '<button type="button" title="Zoom in" data-zoom="in">+</button>',
    '<button type="button" title="Zoom out" data-zoom="out">−</button>',
    '<button type="button" title="Fit to viewport" data-zoom="fit">□</button>',
  ].join('');

  root.addEventListener('click', (event) => {
    const target = event.target as HTMLElement | null;
    const action = target?.getAttribute?.('data-zoom');
    if (!action) return;
    const c = canvas;
    if (action === 'in') c.zoom(c.zoom() * 1.1);
    else if (action === 'out') c.zoom(c.zoom() * 0.9);
    else if (action === 'fit') c.zoom('fit-viewport', 'auto');
  });

  parent.appendChild(root);

  eventBus.on('diagram.destroy', () => {
    root.remove();
  });
}

(ZoomControls as any).$inject = ['canvas', 'eventBus'];

export const zoomControlsModule = {
  __init__: ['m8flowZoomControls'],
  m8flowZoomControls: ['type', ZoomControls],
};

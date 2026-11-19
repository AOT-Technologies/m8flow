/**
 * DOM zoom chrome for diagram-js (no React). Same role as camunda minimap —
 * package-owned modeler/viewer chrome. Used on BPMN Modeler, NavigatedViewer,
 * and the DMN DRD viewer so fit + toolbar zoom match.
 */
import '../assets/zoom-controls.css';

const TITLES = { in: 'Zoom in', out: 'Zoom out', fit: 'Fit to viewport' } as const;
const EXPAND_TITLE = 'Expand view';
const COLLAPSE_TITLE = 'Exit expanded view';
const EXPANDED_CLASS = 'm8flow-bpmn--expanded';
/** Hosts mark a wider wrapper (e.g. canvas + properties panel) to expand with the canvas. */
const EXPAND_ROOT = '[data-m8flow-expand-root]';
const ICON = (paths: string) =>
  `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
const EXPAND_ICON = ICON('<path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/>');
const COLLAPSE_ICON = ICON('<path d="M4 14h6v6"/><path d="M20 10h-6V4"/><path d="M14 10l7-7"/><path d="M3 21l7-7"/>');

type Size = { width: number; height: number };
type Rect = Size & { x: number; y: number };

/** Room for the chrome over the canvas: toolbar row on top, palette on the left. */
export const FILL_PADDING = { top: 80, right: 40, bottom: 40, left: 120 };

/**
 * Viewbox for the expanded view: scale the diagram until it fills the
 * viewport on its shorter side ("cover", not fit-viewport's "contain"), so a
 * wide process is readable and pans sideways. Never past 100%. Starts at the
 * diagram's left / top edge; centres along an axis that has room to spare.
 */
export function fillViewbox(outer: Size, inner: Rect, pad = FILL_PADDING): Rect {
  const availWidth = Math.max(1, outer.width - pad.left - pad.right);
  const availHeight = Math.max(1, outer.height - pad.top - pad.bottom);
  const scale = Math.min(1, Math.max(availWidth / inner.width, availHeight / inner.height));
  const offsetX = pad.left + Math.max(0, (availWidth - inner.width * scale) / 2);
  const offsetY = pad.top + Math.max(0, (availHeight - inner.height * scale) / 2);
  return {
    x: inner.x - offsetX / scale,
    y: inner.y - offsetY / scale,
    width: outer.width / scale,
    height: outer.height / scale,
  };
}

/**
 * `config.zoomControls.parent`: a host element to mount the pill in (like
 * `propertiesPanel.parent`), so the host can lay it out in its own toolbar.
 * Without it, the pill floats bottom-left over the canvas.
 */
export function ZoomControls(
  this: any,
  canvas: any,
  eventBus: any,
  translate: (template: string) => string,
  config?: { parent?: HTMLElement },
) {
  const parent = canvas.getContainer();
  parent.classList.add('m8flow-bpmn');

  const root = document.createElement('div');
  root.className = 'm8flow-bpmn-zoom';
  root.innerHTML = [
    '<button type="button" data-zoom="in">+</button>',
    '<button type="button" data-zoom="out">−</button>',
    '<button type="button" data-zoom="fit">□</button>',
    `<button type="button" data-zoom="expand" aria-pressed="false">${EXPAND_ICON}</button>`,
  ].join('');
  const expandButton = root.querySelector<HTMLButtonElement>('[data-zoom="expand"]')!;
  const expandTarget = (): HTMLElement => parent.closest(EXPAND_ROOT) ?? parent;
  let expanded = false;

  // Re-run on i18n.changed so a language switch reaches an open diagram.
  const setTitles = () => {
    root.querySelectorAll<HTMLButtonElement>('button').forEach((button) => {
      const key =
        button.dataset.zoom === 'expand'
          ? expanded ? COLLAPSE_TITLE : EXPAND_TITLE
          : TITLES[button.dataset.zoom as keyof typeof TITLES];
      if (key) button.title = translate(key);
    });
  };
  setTitles();
  eventBus.on('i18n.changed', setTitles);

  // A CSS overlay, not the Fullscreen API: fullscreen would hide the host's
  // dialogs (script / form editors), which portal to <body>.
  // Re-zoom for the current mode after the canvas changed size. Public
  // (`m8flowZoomControls.refit()`) so a host that resizes the canvas after
  // the toggle (the modeler hiding its properties panel) can refit too.
  this.refit = () => {
    canvas.resized();
    const { outer, inner } = canvas.viewbox();
    if (expanded && inner.width > 0 && inner.height > 0) canvas.viewbox(fillViewbox(outer, inner));
    else canvas.zoom('fit-viewport', 'auto');
  };

  const setExpanded = (next: boolean) => {
    expanded = next;
    expandTarget().classList.toggle(EXPANDED_CLASS, next);
    expandButton.innerHTML = next ? COLLAPSE_ICON : EXPAND_ICON;
    expandButton.setAttribute('aria-pressed', String(next));
    setTitles();
    // Hosts react to the mode (the modeler hides its properties panel).
    eventBus.fire('m8flow.expand.changed', { expanded: next });
    this.refit();
  };

  // Escape leaves the expanded view, unless it was meant for a label edit or
  // for something outside the diagram (an open dialog).
  const onKeydown = (event: KeyboardEvent) => {
    if (!expanded || event.key !== 'Escape' || event.defaultPrevented) return;
    const target = event.target as HTMLElement;
    if (target.isContentEditable) return;
    if (target !== document.body && !expandTarget().contains(target)) return;
    setExpanded(false);
  };
  document.addEventListener('keydown', onKeydown);

  root.addEventListener('click', (event) => {
    const target = event.target as HTMLElement | null;
    const action = target?.closest?.('[data-zoom]')?.getAttribute('data-zoom');
    if (!action) return;
    const c = canvas;
    if (action === 'in') c.zoom(c.zoom() * 1.1);
    else if (action === 'out') c.zoom(c.zoom() * 0.9);
    else if (action === 'fit') c.zoom('fit-viewport', 'auto');
    else if (action === 'expand') setExpanded(!expanded);
  });

  if (config?.parent) root.classList.add('m8flow-bpmn-zoom--inline');
  (config?.parent ?? parent).appendChild(root);

  eventBus.on('diagram.destroy', () => {
    document.removeEventListener('keydown', onKeydown);
    expandTarget().classList.remove(EXPANDED_CLASS);
    root.remove();
  });
}

(ZoomControls as any).$inject = ['canvas', 'eventBus', 'translate', 'config.zoomControls'];

export const zoomControlsModule = {
  __init__: ['m8flowZoomControls'],
  m8flowZoomControls: ['type', ZoomControls],
};

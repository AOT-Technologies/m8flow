/**
 * Minimize button for the modeler palette. diagram-js already has the
 * closed state (`palette.close()` hides the entries and shows its own
 * `.djs-palette-toggle`, which reopens it); this adds the way in and gives
 * that toggle an icon, tooltip and keyboard access (diagram-chrome.css).
 * Open by default.
 */
const CHEVRON_UP =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>';

export function PaletteMinimize(this: any, eventBus: any, palette: any, translate: (template: string) => string) {
  let minimized = false;
  let minimize: HTMLButtonElement | null = null;
  let reopen: HTMLElement | null = null;

  const setTitles = () => {
    if (minimize) minimize.title = translate('Minimize');
    if (reopen) reopen.title = translate('Expand');
  };

  eventBus.on('palette.create', ({ container }: { container: HTMLElement }) => {
    minimize = document.createElement('button');
    minimize.type = 'button';
    minimize.className = 'm8flow-bpmn-palette-minimize';
    minimize.innerHTML = CHEVRON_UP;
    minimize.addEventListener('click', () => {
      minimized = true;
      palette.close();
    });
    container.appendChild(minimize);

    // diagram-js's own click handler on the toggle reopens the palette.
    reopen = container.querySelector<HTMLElement>('.djs-palette-toggle');
    if (reopen) {
      const toggle = reopen;
      toggle.setAttribute('role', 'button');
      toggle.tabIndex = 0;
      toggle.addEventListener('click', () => {
        minimized = false;
      });
      toggle.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        toggle.click();
      });
    }
    setTitles();
  });

  // Expanded view (zoomControls): minimize to give the diagram the room; the
  // user can reopen it, and leaving restores what they had.
  let minimizedBeforeExpand = false;
  eventBus.on('m8flow.expand.changed', ({ expanded }: { expanded: boolean }) => {
    if (expanded) minimizedBeforeExpand = minimized;
    minimized = expanded || minimizedBeforeExpand;
    if (minimized) palette.close();
    else palette.open();
  });

  // Palette re-renders and reopens itself on i18n.changed; run after it
  // (lower priority) so a minimized palette stays minimized.
  eventBus.on('i18n.changed', 500, () => {
    setTitles();
    if (minimized) palette.close();
  });
}

(PaletteMinimize as any).$inject = ['eventBus', 'palette', 'translate'];

export const paletteMinimizeModule = {
  __init__: ['m8flowPaletteMinimize'],
  m8flowPaletteMinimize: ['type', PaletteMinimize],
};

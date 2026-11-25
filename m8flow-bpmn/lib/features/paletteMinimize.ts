/**
 * Minimize button for the modeler palette. diagram-js already has the
 * closed state (`palette.close()` hides the entries and shows its own
 * `.djs-palette-toggle`, which reopens it); this adds the way in and gives
 * that toggle an icon, tooltip and keyboard access (diagram-chrome.css).
 * Open by default.
 */
import { CHEVRON_UP_PATHS, svgIcon } from './svgIcon';

export function PaletteMinimize(this: any, eventBus: any, palette: any, translate: (template: string) => string) {
  let minimized = false;
  let minimize: HTMLButtonElement | null = null;
  let reopen: HTMLElement | null = null;

  const setTitles = () => {
    // aria-label too: these are icon-only, so the label is their name.
    for (const [control, key] of [[minimize, 'Minimize'], [reopen, 'Expand']] as const) {
      if (!control) continue;
      control.title = translate(key);
      control.setAttribute('aria-label', translate(key));
    }
  };

  eventBus.on('palette.create', ({ container }: { container: HTMLElement }) => {
    minimize = document.createElement('button');
    minimize.type = 'button';
    minimize.className = 'm8flow-bpmn-palette-minimize';
    minimize.append(svgIcon(CHEVRON_UP_PATHS, 14));
    minimize.addEventListener('click', () => {
      minimized = true;
      palette.close();
    });
    container.appendChild(minimize);

    // diagram-js's own click handler on the toggle reopens the palette.
    reopen = container.querySelector<HTMLElement>('.djs-palette-toggle');
    if (reopen) {
      const toggle = reopen;
      toggle.addEventListener('click', () => {
        minimized = false;
      });
      // diagram-js renders a <div>; only a non-button needs the button role
      // and Enter / Space handling (a native <button> has both).
      if (toggle.tagName !== 'BUTTON') {
        toggle.setAttribute('role', 'button');
        toggle.tabIndex = 0;
        toggle.addEventListener('keydown', (event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          toggle.click();
        });
      }
    }
    setTitles();
    syncExpanded(palette.isOpen());
  });

  // aria-expanded on both controls tracks the palette's open state.
  const syncExpanded = (open: boolean) => {
    minimize?.setAttribute('aria-expanded', String(open));
    reopen?.setAttribute('aria-expanded', String(open));
  };
  eventBus.on('palette.changed', ({ open }: { open: boolean }) => syncExpanded(open));

  // Expanded view (zoomControls). Runs only when the view enters or leaves
  // expanded mode, not on the user's own minimize / reopen clicks:
  // - entering: remember the current state, then minimize to give the
  //   diagram the room (the user can still reopen it while expanded);
  // - leaving: restore the state from *before* expanding. Changes made while
  //   expanded do not carry over to the normal view.
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

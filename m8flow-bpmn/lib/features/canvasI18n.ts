/**
 * Canvas side of a language switch (BPMN Modeler and DMN DRD).
 *
 * - bpmn-js-spiffworkflow's IoPalette imports diagram-js's default
 *   `translate` function instead of the service, so its titles ("Create
 *   DataInput") stay English. A last-running palette provider translates
 *   every title; one already translated has no dictionary entry and passes
 *   through unchanged.
 * - The palette re-renders on `i18n.changed`, but an open context pad keeps
 *   the entries it was built with; rebuild it.
 */

// Lowest priority runs last over the merged palette entries.
const LAST = 1;

type Translate = (template: string) => string;

export function CanvasI18n(eventBus: any, palette: any, contextPad: any, translate: Translate) {
  palette.registerProvider(LAST, {
    getPaletteEntries: () => (entries: Record<string, { title?: unknown }>) => {
      for (const entry of Object.values(entries)) {
        if (typeof entry.title === 'string') entry.title = translate(entry.title);
      }
      return entries;
    },
  });

  let target: unknown;
  eventBus.on('contextPad.open', (event: { current: { target: unknown } }) => {
    target = event.current.target;
  });
  eventBus.on('contextPad.close', () => {
    target = undefined;
  });
  eventBus.on('i18n.changed', () => {
    if (target && contextPad.isOpen(target)) contextPad.open(target, true);
  });
}

(CanvasI18n as any).$inject = ['eventBus', 'palette', 'contextPad', 'translate'];

export const canvasI18nModule = {
  __init__: ['m8flowCanvasI18n'],
  m8flowCanvasI18n: ['type', CanvasI18n],
};

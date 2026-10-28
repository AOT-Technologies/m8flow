import i18n, { DIAGRAM_NS } from '@/i18n';

/**
 * bpmn-js / dmn-js `translate` service backed by the app's i18next. The English
 * template is the key and the language is read on every call, so a diagram
 * re-render after `i18n.changed` picks up a language switch.
 */
export function translateDiagram(template: string, replacements: Record<string, string> = {}): string {
  const text: string = i18n.getResource(i18n.language, DIAGRAM_NS, template, { keySeparator: false }) ?? template;
  // Same {name} substitution as diagram-js's default translate.
  return text.replace(/{([^}]+)}/g, (_, key: string) => replacements[key] || `{${key}}`);
}

/** Overrides the diagram's `translate` service; pass it in `additionalModules`. */
export const diagramTranslateModule = { translate: ['value', translateDiagram] };

/**
 * Loads the diagram strings, and calls `refresh` when they arrive and on every
 * language switch. Returns the unsubscribe for the effect cleanup.
 */
export function followDiagramLanguage(refresh: () => void): () => void {
  i18n.on('loaded', refresh);
  i18n.on('languageChanged', refresh);
  void i18n.loadNamespaces(DIAGRAM_NS);
  return () => {
    i18n.off('loaded', refresh);
    i18n.off('languageChanged', refresh);
  };
}

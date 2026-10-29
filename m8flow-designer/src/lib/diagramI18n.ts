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
  let active = true;
  let refreshing = false;

  const triggerRefresh = () => {
    if (!active || refreshing) return;
    refreshing = true;
    try {
      refresh();
    } finally {
      queueMicrotask(() => {
        refreshing = false;
      });
    }
  };

  const onLanguageChanged = () => {
    void i18n.loadNamespaces(DIAGRAM_NS).then(triggerRefresh);
  };

  const onLoaded = (loaded: unknown) => {
    if (!active) return;
    if (loaded && typeof loaded === 'object') {
      const payload = loaded as Record<string, Record<string, boolean>>;
      if (payload[i18n.language]?.[DIAGRAM_NS]) {
        triggerRefresh();
      }
    }
  };

  i18n.on('loaded', onLoaded);
  i18n.on('languageChanged', onLanguageChanged);
  void i18n.loadNamespaces(DIAGRAM_NS).then(triggerRefresh);

  return () => {
    active = false;
    i18n.off('loaded', onLoaded);
    i18n.off('languageChanged', onLanguageChanged);
  };
}

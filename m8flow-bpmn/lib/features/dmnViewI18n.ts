/**
 * DMN decision-table and expression views (inferno) render once and only
 * re-render on model changes, so a language switch never reaches an open
 * view. Re-render in place on `i18n.changed` — no re-import, so the command
 * stack (undo, and the host's dirty tracking) is untouched. Views that are
 * not open re-render when dmn-js opens them.
 *
 * No `inferno` import: its types declare a global JSX namespace that breaks
 * the designer's React type-check.
 */

type Translate = (template: string) => string;

/**
 * Decision table: TableComponent force-updates the whole table (headers,
 * cells, the View DRD button) when its root changes; every component
 * translates in render(). dmn-js's CSS writes the empty-header placeholders
 * ('Input' / 'Output'); dmn.css reads them from these properties instead.
 */
export function DecisionTableI18n(eventBus: any, sheet: any, renderer: any, translate: Translate) {
  const container: HTMLElement = renderer.getContainer();
  const setPlaceholders = () => {
    // JSON quoting is valid CSS string syntax.
    container.style.setProperty('--m8flow-dmn-input-placeholder', JSON.stringify(translate('Input')));
    container.style.setProperty('--m8flow-dmn-output-placeholder', JSON.stringify(translate('Output')));
  };
  setPlaceholders();

  eventBus.on('root.added', setPlaceholders);

  eventBus.on('i18n.changed', () => {
    setPlaceholders();
    const root = sheet.getRoot();
    if (root) eventBus.fire('elements.changed', { elements: [root] });
  });
}

(DecisionTableI18n as any).$inject = ['eventBus', 'sheet', 'renderer', 'translate'];

/** Literal / boxed expression: mounting again patches the existing tree with the same components. */
export function ExpressionViewI18n(eventBus: any) {
  eventBus.on('i18n.changed', () => eventBus.fire('renderer.mount'));
}

(ExpressionViewI18n as any).$inject = ['eventBus'];

export const decisionTableI18nModule = {
  __init__: ['m8flowDecisionTableI18n'],
  m8flowDecisionTableI18n: ['type', DecisionTableI18n],
};

export const expressionViewI18nModule = {
  __init__: ['m8flowExpressionViewI18n'],
  m8flowExpressionViewI18n: ['type', ExpressionViewI18n],
};

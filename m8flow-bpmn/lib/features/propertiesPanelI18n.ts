/**
 * Properties-panel side of a language switch, for the BPMN and DMN panels.
 *
 * - diagram-js re-renders the palette on `i18n.changed`, but the panels only
 *   re-render on `propertiesPanel.providersChanged`; bridge the two.
 * - bpmn-js-spiffworkflow and dmn-js-properties-panel pass some text raw
 *   instead of through `translate`: group headers (Signals, General), entry
 *   labels and descriptions (Guest options), description-entry text (the
 *   Input/Output ℹ️ note) and button text (Launch Editor). Their list groups
 *   also get no `translate` prop, so ListGroup falls back to English
 *   ("Create"). A last-running provider fixes all of it; text that is
 *   already translated has no dictionary entry and passes through unchanged.
 *
 * No imports: preact / @bpmn-io/properties-panel here would add a second
 * resolution path the designer's Vitest cannot load.
 */

// Lowest priority runs last in the getGroups middleware chain.
const LAST = 1;

type Translate = (template: string) => string;
type Entry = {
  component?: any;
  label?: unknown;
  description?: unknown;
  value?: unknown;
  getValue?: unknown;
  translate?: Translate;
  // ListGroup items (Data Objects, Inputs): their label is the user's name, their entries are UI.
  items?: { entries?: Entry[] }[];
};

export function PropertiesPanelI18n(eventBus: any, propertiesPanel: any, translate: Translate) {
  eventBus.on('i18n.changed', () => eventBus.fire('propertiesPanel.providersChanged'));

  // One wrapper per component, so Preact keeps the entry mounted across renders.
  const wrappers = new WeakMap<object, unknown>();
  const isWrapper = new WeakSet<object>();

  /**
   * What a Spiff entry renders: its Launch Editor / Search buttons hardcode
   * their text, and it calls TextAreaEntry & co. without `translate`, so their
   * built-in "Open pop-up editor" falls back to English, and some set a raw
   * `label` / `description` on it (`<SelectEntry label="Which message …">`).
   * Translate the button; treat the rendered component and its component
   * children (never DOM elements, which have a real `translate` attribute)
   * like an entry. Vnodes are created fresh on every render, so they are
   * updated in place.
   */
  const localize = (vnode: any) => {
    if (vnode?.type === 'button' && typeof vnode.props.children === 'string') {
      vnode.props.children = translate(vnode.props.children);
      return vnode;
    }
    for (const node of [vnode, ...[vnode?.props?.children].flat()]) {
      if (typeof node?.type !== 'function') continue;
      const { props } = node;
      if (typeof props.label === 'string') props.label = translate(props.label);
      if (typeof props.description === 'string') props.description = translate(props.description);
      // Description / TooltipWrapper (the ones with `forId`) hold UI text in `value`; elsewhere it's the user's data.
      if ('forId' in props && typeof props.value === 'string') props.value = translate(props.value);
      if (props.translate === undefined) props.translate = translate;
    }
    return vnode;
  };

  const withTranslatedOutput = (component: any) => {
    // Class and memo components can't be called as plain functions.
    if (
      typeof component !== 'function' ||
      isWrapper.has(component) ||
      component.prototype?.render ||
      component.prototype?.isReactComponent
    ) {
      return component;
    }
    if (!wrappers.has(component)) {
      const wrapper = function TranslatedEntry(props: unknown, context: unknown) {
        return localize(component(props, context));
      };
      wrappers.set(component, wrapper);
      isWrapper.add(wrapper);
    }
    return wrappers.get(component);
  };

  const translateEntry = (entry: Entry) => {
    if (typeof entry.label === 'string') entry.label = translate(entry.label);
    if (typeof entry.description === 'string') entry.description = translate(entry.description);
    // A static value is DescriptionEntry text; input entries read the user's data through getValue.
    if (typeof entry.value === 'string' && !entry.getValue) entry.value = translate(entry.value);
    if (entry.component) entry.component = withTranslatedOutput(entry.component);
    entry.translate ??= translate;
    entry.items?.forEach((item) => item.entries?.forEach(translateEntry));
  };

  propertiesPanel.registerProvider(LAST, {
    getGroups: () => (groups: (Entry & { entries?: Entry[] })[]) => {
      for (const group of groups) {
        if (typeof group.label === 'string') group.label = translate(group.label);
        group.translate ??= translate;
        group.entries?.forEach(translateEntry);
        group.items?.forEach((item) => item.entries?.forEach(translateEntry));
      }
      return groups;
    },
  });
}

(PropertiesPanelI18n as any).$inject = ['eventBus', 'propertiesPanel', 'translate'];

export const propertiesPanelI18nModule = {
  __init__: ['m8flowPropertiesPanelI18n'],
  m8flowPropertiesPanelI18n: ['type', PropertiesPanelI18n],
};

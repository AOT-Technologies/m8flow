/**
 * BPMN-specific context pad provider.
 *
 * @implements {BaseContextPadProvider}
 *
 */
export default class ContextPadProvider implements BaseContextPadProvider {
  static $inject: string[];

  /**
   * @param config
   * @param injector
   * @param eventBus
   * @param contextPad
   * @param modeling
   * @param elementFactory
   * @param connect
   * @param create
   * @param popupMenu
   * @param canvas
   * @param rules
   * @param translate
   * @param appendPreview
   */
  constructor(config: ContextPadConfig, injector: Injector, eventBus: EventBus, contextPad: ContextPad, modeling: Modeling, elementFactory: ElementFactory, connect: Connect, create: Create, popupMenu: PopupMenu, canvas: any, rules: Rules, translate: Translate, appendPreview: AppendPreview);

  /**
   * @param elements
   *
   * @return
   */
  getMultiElementContextPadEntries(elements: Element[]): ContextPadEntries;

  /**
   * @param element
   *
   * @return
   */
  getContextPadEntries(element: Element): ContextPadEntries;
}

type Injector = import('didi').Injector;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type ContextPad = import('diagram-js/lib/features/context-pad/ContextPad').default;
type Modeling = import('../modeling/Modeling').default;
type ElementFactory = import('../modeling/ElementFactory').default;
type AppendPreview = import('../append-preview/AppendPreview').default;
type Connect = import('diagram-js/lib/features/connect/Connect').default;
type Create = import('diagram-js/lib/features/create/Create').default;
type PopupMenu = import('diagram-js/lib/features/popup-menu/PopupMenu').default;
export type Canvas = any;
type Rules = import('diagram-js/lib/features/rules/Rules').default;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
type Element = import('../../model/Types').Element;
type ModdleElement = import('../../model/Types').ModdleElement;
type BaseContextPadProvider = import('diagram-js/lib/features/context-pad/ContextPadProvider').default<Element>;
type ContextPadEntries = import('diagram-js/lib/features/context-pad/ContextPadProvider').ContextPadEntries;
type ContextPadEntry = import('diagram-js/lib/features/context-pad/ContextPadProvider').ContextPadEntry;

export type ContextPadConfig = {
    autoPlace?: boolean;
};

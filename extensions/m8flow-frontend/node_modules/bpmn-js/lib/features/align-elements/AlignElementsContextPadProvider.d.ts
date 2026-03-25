/**
 * A provider for the `Align elements` context pad entry.
 *
 * @implements {ContextPadProvider}
 *
 */
export default class AlignElementsContextPadProvider implements ContextPadProvider {
  static $inject: string[];

  /**
   * @param contextPad
   * @param popupMenu
   * @param translate
   * @param canvas
   */
  constructor(contextPad: ContextPad, popupMenu: PopupMenu, translate: Translate, canvas: Canvas);

  /**
   * @param elements
   *
   * @return
   */
  getMultiElementContextPadEntries(elements: Element[]): ContextPadEntries;
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type ContextPad = import('diagram-js/lib/features/context-pad/ContextPad').default;
type PopupMenu = import('diagram-js/lib/features/popup-menu/PopupMenu').default;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
type Element = import('../../model/Types').Element;
type ContextPadEntries = import('diagram-js/lib/features/context-pad/ContextPad').ContextPadEntries;
type ContextPadProvider = import('diagram-js/lib/features/context-pad/ContextPadProvider').default<Element>;

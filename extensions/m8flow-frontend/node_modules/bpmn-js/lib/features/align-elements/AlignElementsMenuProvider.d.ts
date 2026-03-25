/**
 * A provider for the `Align elements` popup menu.
 *
 * @implements {PopupMenuProvider}
 *
 */
export default class AlignElementsMenuProvider implements PopupMenuProvider {
  static $inject: string[];

  /**
   * @param popupMenu
   * @param alignElements
   * @param translate
   * @param rules
   */
  constructor(popupMenu: PopupMenu, alignElements: AlignElements, translate: Translate, rules: Rules);

  /**
   * @param target
   *
   * @return
   */
  getPopupMenuEntries(target: PopupMenuTarget): PopupMenuEntries;
}

type AlignElements = import('diagram-js/lib/features/align-elements/AlignElements').default;
type PopupMenu = import('diagram-js/lib/features/popup-menu/PopupMenu').default;
type Rules = import('diagram-js/lib/features/rules/Rules').default;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
type PopupMenuEntries = import('diagram-js/lib/features/popup-menu/PopupMenu').PopupMenuEntries;
type PopupMenuProvider = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').default;
type PopupMenuTarget = import('diagram-js/lib/features/popup-menu/PopupMenu').PopupMenuTarget;

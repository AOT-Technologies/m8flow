/**
 * A provider for the distribute elements popup menu.
 *
 * @implements {PopupMenuProvider}
 *
 */
export default class DistributeElementsMenuProvider implements PopupMenuProvider {
  static $inject: string[];

  /**
   * @param popupMenu
   * @param distributeElements
   * @param translate
   * @param rules
   */
  constructor(popupMenu: PopupMenu, distributeElements: DistributeElements, translate: Translate, rules: Rules);

  /**
   * @param target
   *
   * @return
   */
  getPopupMenuEntries(target: PopupMenuTarget): PopupMenuEntries;
}

type PopupMenu = import('diagram-js/lib/features/popup-menu/PopupMenu').default;
type DistributeElements = import('./BpmnDistributeElements').default;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
type Rules = import('diagram-js/lib/features/rules/Rules').default;
type PopupMenuEntries = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').PopupMenuEntries;
type PopupMenuProvider = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').default;
type PopupMenuTarget = import('diagram-js/lib/features/popup-menu/PopupMenu').PopupMenuTarget;

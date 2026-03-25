/**
 * A BPMN-specific popup menu provider.
 *
 * @implements {PopupMenuProvider}
 *
 */
export default class ReplaceMenuProvider implements PopupMenuProvider {
  static $inject: string[];

  /**
   * @param bpmnFactory
   * @param popupMenu
   * @param modeling
   * @param moddle
   * @param bpmnReplace
   * @param rules
   * @param translate
   * @param moddleCopy
   */
  constructor(bpmnFactory: BpmnFactory, popupMenu: PopupMenu, modeling: Modeling, moddle: Moddle, bpmnReplace: BpmnReplace, rules: any, translate: Translate, moddleCopy: ModdleCopy);

  /**
   * @param target
   *
   * @return
   */
  getPopupMenuEntries(target: PopupMenuTarget): PopupMenuEntries;

  /**
   * @param target
   *
   * @return
   */
  getPopupMenuHeaderEntries(target: PopupMenuTarget): import("diagram-js/lib/features/popup-menu/PopupMenuProvider").PopupMenuHeaderEntries;
}

type BpmnFactory = import('../modeling/BpmnFactory').default;
type PopupMenu = import('diagram-js/lib/features/popup-menu/PopupMenu').default;
type Modeling = import('../modeling/Modeling').default;
type BpmnReplace = import('../replace/BpmnReplace').default;
export type Rules = any;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
type ModdleCopy = import('../copy-paste/ModdleCopy').default;
type Element = import('../../model/Types').Element;
type Moddle = import('../../model/Types').Moddle;
type PopupMenuEntries = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').PopupMenuEntries;
type PopupMenuEntry = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').PopupMenuEntry;
type PopupMenuEntryAction = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').PopupMenuEntryAction;
type PopupMenuHeaderEntries = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').PopupMenuHeaderEntries;
type PopupMenuProvider = import('diagram-js/lib/features/popup-menu/PopupMenuProvider').default;
type PopupMenuTarget = import('diagram-js/lib/features/popup-menu/PopupMenu').PopupMenuTarget;
export type ReplaceOption = any;

/**
 * Returns true, if an element is from a different type
 * than a target definition. Takes into account the type,
 * event definition type and triggeredByEvent property.
 *
 * @param element
 *
 * @return
 */
export function isDifferentType(element: Element): DifferentTypeValidator;

type Element = import('../../../model/Types').Element;
type PopupMenuTarget = import('diagram-js/lib/features/popup-menu/PopupMenu').PopupMenuTarget;
export type DifferentTypeValidator = (entry: PopupMenuTarget) => boolean;

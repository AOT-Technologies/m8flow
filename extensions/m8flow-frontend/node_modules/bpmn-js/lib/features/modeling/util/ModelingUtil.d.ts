/**
 * Return the parent of the element with any of the given types.
 *
 * @param element
 * @param anyType
 *
 * @return
 */
export function getParent(element: Element, anyType: string | string[]): Element | null;

/**
 * Determines if the local modeling direction is vertical or horizontal.
 *
 * @param element
 * @param elementRegistry - provide to consider parent diagram direction
 *
 * @return false for vertical pools, lanes and their children. true otherwise
 */
export function isDirectionHorizontal(element: Element, elementRegistry?: ElementRegistry): boolean;

type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type Element = import('../../../model/Types').Element;
export { is, isAny } from "../../../util/ModelUtil";

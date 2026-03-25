/**
 * @param element
 * @param di
 *
 * @return
 */
export function isExpanded(element: Element, di?: ModdleElement): boolean;

/**
 * @param element
 *
 * @return
 */
export function isHorizontal(element: Element): boolean;

/**
 * @param element
 *
 * @return
 */
export function isInterrupting(element: Element): boolean;

/**
 * @param element
 *
 * @return
 */
export function isEventSubProcess(element: Element): boolean;

/**
 * @param element
 * @param eventType
 *
 * @return
 */
export function hasEventDefinition(element: Element, eventType: string): boolean;

/**
 * @param element
 *
 * @return
 */
export function hasErrorEventDefinition(element: Element): boolean;

/**
 * @param element
 *
 * @return
 */
export function hasEscalationEventDefinition(element: Element): boolean;

/**
 * @param element
 *
 * @return
 */
export function hasCompensateEventDefinition(element: Element): boolean;

type Element = import('../model/Types').Element;
type ModdleElement = import('../model/Types').ModdleElement;

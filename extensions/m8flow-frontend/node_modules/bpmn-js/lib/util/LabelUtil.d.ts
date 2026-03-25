/**
 * Return true if the given semantic has an external label.
 *
 * @param semantic
 *
 * @return
 */
export function isLabelExternal(semantic: Element): boolean;

/**
 * Return true if the given element has an external label.
 *
 * @param element
 *
 * @return
 */
export function hasExternalLabel(element: Element): boolean;

/**
 * Get the position of a sequence flow label.
 *
 * @param  waypoints
 *
 * @return
 */
export function getFlowLabelPosition(waypoints: Point[]): Point;

/**
 * Get the middle of a number of waypoints.
 *
 * @param  waypoints
 *
 * @return
 */
export function getWaypointsMid(waypoints: Point[]): Point;

/**
 * Get the middle of the external label of an element.
 *
 * @param element
 *
 * @return
 */
export function getExternalLabelMid(element: Element): Point;

/**
 * Return the bounds of an elements label, parsed from the elements DI or
 * generated from its bounds.
 *
 * @param di
 * @param element
 *
 * @return
 */
export function getExternalLabelBounds(di: ModdleElement, element: Element): Rect;

/**
 * @param element
 *
 * @return
 */
export function getLabel(element: Element): string;

/**
 * @param element
 * @param text
 *
 * @return
 */
export function setLabel(element: Element, text: string): Element;

export { isLabel } from "diagram-js/lib/util/ModelUtil";

export namespace DEFAULT_LABEL_SIZE {
    const width: number;
    const height: number;
}

export const FLOW_LABEL_INDENT: number;
type Point = import('diagram-js/lib/util/Types').Point;
type Rect = import('diagram-js/lib/util/Types').Rect;
type Element = import('../model/Types').Element;
type ModdleElement = import('../model/Types').ModdleElement;

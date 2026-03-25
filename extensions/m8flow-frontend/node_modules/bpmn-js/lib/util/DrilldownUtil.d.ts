/**
 * Get primary shape ID for a plane.
 *
 * @param  element
 *
 * @return
 */
export function getShapeIdFromPlane(element: Element | ModdleElement): string;

/**
 * Get plane ID for a primary shape.
 *
 * @param  element
 *
 * @return
 */
export function getPlaneIdFromShape(element: Element | ModdleElement): string;

/**
 * Get plane ID for primary shape ID.
 *
 * @param id
 *
 * @return
 */
export function toPlaneId(id: string): string;

/**
 * Check wether element is plane.
 *
 * @param  element
 *
 * @return
 */
export function isPlane(element: Element | ModdleElement): boolean;

export const planeSuffix: string;
type Element = import('../model/Types').Element;
type ModdleElement = import('../model/Types').ModdleElement;

/**
 * Checks if eventDefinition of the given element matches with semantic type.
 *
 * @param event
 * @param eventDefinitionType
 *
 * @return
 */
export function isTypedEvent(event: any, eventDefinitionType: string): boolean;

/**
 * Check if element is a throw event.
 *
 * @param event
 *
 * @return
 */
export function isThrowEvent(event: any): boolean;

/**
 * Check if element is a throw event.
 *
 * @param element
 *
 * @return
 */
export function isCollection(element: any): boolean;

/**
 * @param element
 * @param defaultColor
 * @param overrideColor
 *
 * @return
 */
export function getFillColor(element: any, defaultColor?: string, overrideColor?: string): string;

/**
 * @param element
 * @param defaultColor
 * @param overrideColor
 *
 * @return
 */
export function getStrokeColor(element: any, defaultColor?: string, overrideColor?: string): string;

/**
 * @param element
 * @param defaultColor
 * @param defaultStrokeColor
 * @param overrideColor
 *
 * @return
 */
export function getLabelColor(element: any, defaultColor?: string, defaultStrokeColor?: string, overrideColor?: string): string;

/**
 * @param shape
 *
 * @return path
 */
export function getCirclePath(shape: any): string;

/**
 * @param shape
 * @param borderRadius
 *
 * @return path
 */
export function getRoundRectPath(shape: any, borderRadius?: number): string;

/**
 * @param shape
 *
 * @return path
 */
export function getDiamondPath(shape: any): string;

/**
 * @param shape
 *
 * @return path
 */
export function getRectPath(shape: any): string;

/**
 * Get width and height from element or overrides.
 *
 * @param bounds
 * @param overrides
 *
 * @returns
 */
export function getBounds(bounds: Dimensions | Rect | ShapeLike, overrides?: any): Dimensions;

/**
 * Get width from element or overrides.
 *
 * @param bounds
 * @param overrides
 *
 * @returns
 */
export function getWidth(bounds: Dimensions | Rect | ShapeLike, overrides?: any): number;

/**
 * Get height from element or overrides.
 *
 * @param bounds
 * @param overrides
 *
 * @returns
 */
export function getHeight(bounds: Dimensions | Rect | ShapeLike, overrides?: any): number;

export const black: string;
export const white: string;
export type ModdleElement = any;
export type Element = any;
export type ShapeLike = any;
type Dimensions = import('diagram-js/lib/util/Types').Dimensions;
type Rect = import('diagram-js/lib/util/Types').Rect;
export { getDi, getBusinessObject as getSemantic } from "../util/ModelUtil";

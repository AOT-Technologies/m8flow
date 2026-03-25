/**
 * Get the position for given new target relative to the source it will be
 * connected to.
 *
 * @param  source
 * @param  element
 * @param  elementRegistry
 *
 * @return
 */
export function getNewShapePosition(source: Shape, element: Shape, elementRegistry: ElementRegistry): Point;

/**
 * Get the position for given new flow node. Try placing the flow node right/bottom of
 * the source.
 *
 * @param source
 * @param element
 * @param placeHorizontally Whether to place the new element horizontally
 *
 * @return
 */
export function getFlowNodePosition(source: Shape, element: Shape, placeHorizontally: boolean): Point;

/**
 * Get the position for given text annotation. Try placing the text annotation
 * top-right of the source (bottom-right in vertical layouts).
 *
 * @param source
 * @param element
 * @param placeHorizontally Whether to place the new element horizontally
 *
 * @return
 */
export function getTextAnnotationPosition(source: Shape, element: Shape, placeHorizontally: boolean): Point;

/**
 * Get the position for given new data element. Try placing the data element
 * bottom-right of the source (bottom-left in vertical layouts).
 *
 * @param source
 * @param element
 * @param placeHorizontally Whether to place the new element horizontally
 *
 * @return
 */
export function getDataElementPosition(source: Shape, element: Shape, placeHorizontally: boolean): Point;

type Shape = import('../../model/Types').Shape;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type Point = import('diagram-js/lib/util/Types').Point;
type DirectionTRBL = import('diagram-js/lib/util/Types').DirectionTRBL;

/**
 * Return all lanes that are children of the given shape.
 *
 * @param  shape
 * @param  collectedShapes
 *
 * @return
 */
export function collectLanes(shape: Shape, collectedShapes?: Shape[]): Shape[];

/**
 * Return all lanes that are direct children of the given shape.
 *
 * @param shape
 *
 * @return
 */
export function getChildLanes(shape: Shape): Shape[];

/**
 * Return the parent shape of the given lane.
 *
 * @param shape
 *
 * @return
 */
export function getLanesRoot(shape: Shape): Shape;

/**
 * Compute the required resize operations for lanes
 * adjacent to the given shape, assuming it will be
 * resized to the given new bounds.
 *
 * @param shape
 * @param newBounds
 *
 * @return
 */
export function computeLanesResize(shape: Shape, newBounds: Rect): {
    shape: Shape;
    newBounds: Rect;
}[];

export const LANE_INDENTATION: number;
type Shape = import('../../../model/Types').Shape;
type Rect = import('diagram-js/lib/util/Types').Rect;

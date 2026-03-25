/**
 * @param position
 * @param targetBounds
 *
 * @return
 */
export function getBoundaryAttachment(position: Point, targetBounds: Rect): DirectionTRBL | null;

type DirectionTRBL = import('diagram-js/lib/util/Types').DirectionTRBL;
type Point = import('diagram-js/lib/util/Types').Point;
type Rect = import('diagram-js/lib/util/Types').Rect;

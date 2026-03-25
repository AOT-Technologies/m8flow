/**
 * Calculate the new point after the connection waypoints got updated.
 *
 * @param position
 * @param newWaypoints
 * @param oldWaypoints
 * @param hints
 *
 * @return
 */
export function getConnectionAdjustment(
  position: Point,
  newWaypoints: Point[],
  oldWaypoints: Point[],
  hints: FindNewLineStartIndexHints
): Point;

type Point = import('diagram-js/lib/util/Types').Point;
type FindNewLineStartIndexHints = import('./LayoutUtil').FindNewLineStartIndexHints;

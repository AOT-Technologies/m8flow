/**
 * Returns the intersection between two line segments a and b.
 *
 * @param l1s
 * @param l1e
 * @param l2s
 * @param l2e
 *
 * @return
 */
export default function lineIntersect(l1s: Point, l1e: Point, l2s: Point, l2e: Point): Point;

type Point = import('diagram-js/lib/util/Types').Point;

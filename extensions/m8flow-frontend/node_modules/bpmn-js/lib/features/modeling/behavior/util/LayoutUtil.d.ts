/**
 * @param oldWaypoints
 * @param newWaypoints
 * @param attachment
 * @param hints
 *
 * @return
 */
export function findNewLineStartIndex(
  oldWaypoints: Point[],
  newWaypoints: Point[],
  attachment: Attachment,
  hints: FindNewLineStartIndexHints
): number;

/**
 * Calculate the required adjustment (move delta) for the given point
 * after the connection waypoints got updated.
 *
 * @param position
 * @param newWaypoints
 * @param oldWaypoints
 * @param hints
 *
 * @return result
 */
export function getAnchorPointAdjustment(position: Point, newWaypoints: Point[], oldWaypoints: Point[], hints: FindNewLineStartIndexHints): AnchorPointAdjustment;

type Point = import('diagram-js/lib/util/Types').Point;
type Attachment = import('./LineAttachmentUtil').Attachment;

export type AnchorPointAdjustment = {
    point: Point;
    delta: Point;
};

export type FindNewLineStartIndexHints = {
    segmentMove?: {
        segmentStartIndex: number;
        newSegmentStartIndex: number;
    };
    bendpointMove?: {
        insert: boolean;
        bendpointIndex: number;
    };
    connectionStart: boolean;
    connectionEnd: boolean;
};

/**
 * @param oldWaypoints
 * @param newWaypoints
 * @param attachment
 * @param hints
 *
 * @return
 */
export function findNewLabelLineStartIndex(
  oldWaypoints: Point[],
  newWaypoints: Point[],
  attachment: Attachment,
  hints: FindNewLineStartIndexHints
): number;

/**
 * Calculate the required adjustment (move delta) for the given label
 * after the connection waypoints got updated.
 *
 * @param label
 * @param newWaypoints
 * @param oldWaypoints
 * @param hints
 *
 * @return
 */
export function getLabelAdjustment(label: Label, newWaypoints: Point[], oldWaypoints: Point[], hints: FindNewLineStartIndexHints): Point;

type Attachment = import('./LineAttachmentUtil').Attachment;
type FindNewLineStartIndexHints = import('./LayoutUtil').FindNewLineStartIndexHints;
type Label = import('../../../../model/Types').Label;
type Point = import('diagram-js/lib/util/Types').Point;

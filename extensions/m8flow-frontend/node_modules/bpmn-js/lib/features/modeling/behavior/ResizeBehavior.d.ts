/**
 * @param laneShape
 * @param resizeDirection
 * @param balanced
 *
 * @return
 */
export function getParticipantResizeConstraints(laneShape: Shape, resizeDirection: Direction, balanced?: boolean): {
    min: RectTRBL;
    max: RectTRBL;
};

/**
 * @type {Dimensions}
 */
export const GROUP_MIN_DIMENSIONS: Dimensions;

/**
 * @type {Dimensions}
 */
export const LANE_MIN_DIMENSIONS: Dimensions;

/**
 * @type {Dimensions}
 */
export const VERTICAL_LANE_MIN_DIMENSIONS: Dimensions;

/**
 * @type {Dimensions}
 */
export const PARTICIPANT_MIN_DIMENSIONS: Dimensions;

/**
 * @type {Dimensions}
 */
export const VERTICAL_PARTICIPANT_MIN_DIMENSIONS: Dimensions;

/**
 * @type {Dimensions}
 */
export const SUB_PROCESS_MIN_DIMENSIONS: Dimensions;

/**
 * @type {Dimensions}
 */
export const TEXT_ANNOTATION_MIN_DIMENSIONS: Dimensions;

/**
 * Set minimum bounds/resize constraints on resize.
 *
 */
export default class ResizeBehavior {
    static $inject: string[];
    /**
     * @param eventBus
     */
    constructor(eventBus: EventBus);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Shape = import('../../../model/Types').Shape;
type Dimensions = import('diagram-js/lib/util/Types').Dimensions;
type Direction = import('diagram-js/lib/util/Types').Direction;
type RectTRBL = import('diagram-js/lib/util/Types').RectTRBL;
declare var min: (...values: number[]) => number;
declare var max: (...values: number[]) => number;
export {};

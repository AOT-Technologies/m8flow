/**
 * Calculates a reference point delta relative to a new position
 * of a certain element's bounds
 *
 * @param referencePoint
 * @param oldBounds
 * @param newBounds
 *
 * @return
 */
export function getReferencePointDelta(referencePoint: Point, oldBounds: Rect, newBounds: Rect): Point;

/**
 * Generates the nearest point (reference point) for a given point
 * onto given set of lines
 *
 * @param point
 * @param lines
 *
 * @return
 */
export function getReferencePoint(point: Point, lines: Line[]): Point;

/**
 * Convert the given bounds to a lines array containing all edges
 *
 * @param bounds
 *
 * @return
 */
export function asEdges(bounds: Rect | Point): Line[];

/**
 * A component that makes sure that external labels are added
 * together with respective elements and properly updated (DI wise)
 * during move.
 *
 */
export default class LabelBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param modeling
     * @param bpmnFactory
     * @param textRenderer
     */
    constructor(eventBus: EventBus, modeling: Modeling, bpmnFactory: BpmnFactory, textRenderer: TextRenderer);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;
type BpmnFactory = import('../BpmnFactory').default;
type TextRenderer = import('../../../draw/TextRenderer').default;
type Point = import('diagram-js/lib/util/Types').Point;
type Rect = import('diagram-js/lib/util/Types').Rect;
export type Line = Point[];
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

/**
 * Snap during create and move.
 *
 */
export default class BpmnCreateMoveSnapping extends CreateMoveSnapping {
    /**
     * @param eventBus
     * @param injector
     */
    constructor(eventBus: EventBus, injector: Injector);
    /**
     * @param event
     *
     * @return
     */
    initSnap(event: Event): SnapContext;
    /**
     * @param snapPoints
     * @param shape
     * @param target
     *
     * @return
     */
    addSnapTargetPoints(snapPoints: SnapPoints, shape: Shape, target: Shape): SnapPoints;
    /**
     * @param shape
     * @param target
     *
     * @return
     */
    getSnapTargets(shape: Shape, target: Shape): Shape[];
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Injector = import('didi').Injector;
type SnapContext = import('diagram-js/lib/features/snapping/SnapContext').default;
type SnapPoints = import('diagram-js/lib/features/snapping/SnapContext').SnapPoints;
type Event = import('diagram-js/lib/core/EventBus').Event;
type Element = import('../../model/Types').Element;
type Shape = import('../../model/Types').Shape;
import CreateMoveSnapping from 'diagram-js/lib/features/snapping/CreateMoveSnapping';

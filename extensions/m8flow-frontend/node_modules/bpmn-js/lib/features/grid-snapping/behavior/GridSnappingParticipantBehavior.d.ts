export default class GridSnappingParticipantBehavior {
    static $inject: string[];
    /**
     * @param canvas
     * @param eventBus
     * @param gridSnapping
     */
    constructor(canvas: Canvas, eventBus: EventBus, gridSnapping: GridSnapping);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type GridSnapping = import('diagram-js/lib/features/grid-snapping/GridSnapping').default;

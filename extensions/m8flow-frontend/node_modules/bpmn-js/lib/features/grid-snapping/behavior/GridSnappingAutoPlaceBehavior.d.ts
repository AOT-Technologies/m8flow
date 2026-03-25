export default class GridSnappingAutoPlaceBehavior {
    static $inject: string[];
    /**
     * @param eventBus
     * @param gridSnapping
     * @param elementRegistry
     */
    constructor(eventBus: EventBus, gridSnapping: GridSnapping, elementRegistry: ElementRegistry);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type GridSnapping = import('diagram-js/lib/features/grid-snapping/GridSnapping').default;
type Axis = import('diagram-js/lib/util/Types').Axis;

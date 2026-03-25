/**
 * Invoke {@link Modeling#resizeLane} instead of {@link Modeling#resizeShape}
 * when resizing a lane or participant shape.
 *
 */
export default class ResizeLaneBehavior {
    static $inject: string[];
    /**
     * @param eventBus
     * @param modeling
     */
    constructor(eventBus: EventBus, modeling: Modeling);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;

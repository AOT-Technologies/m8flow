export default class BpmnDiOrdering {
    static $inject: string[];
    /**
     * @param eventBus
     * @param canvas
     */
    constructor(eventBus: EventBus, canvas: Canvas);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Canvas = import('diagram-js/lib/core/Canvas').default;

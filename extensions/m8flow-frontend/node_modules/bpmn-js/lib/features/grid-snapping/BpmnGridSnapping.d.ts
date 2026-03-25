export default class BpmnGridSnapping {
    static $inject: string[];
    /**
     * @param eventBus
     */
    constructor(eventBus: EventBus);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;

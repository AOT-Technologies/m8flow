/**
 * BPMN auto-place behavior.
 *
 */
export default class AutoPlace {
    static $inject: string[];
    /**
     * @param eventBus
     * @param elementRegistry
     */
    constructor(eventBus: EventBus, elementRegistry: ElementRegistry);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;

/**
 * BPMN-specific copy & paste.
 *
 */
export default class BpmnCopyPaste {
    static $inject: string[];
    /**
     * @param bpmnFactory
     * @param eventBus
     * @param moddleCopy
     */
    constructor(bpmnFactory: BpmnFactory, eventBus: EventBus, moddleCopy: ModdleCopy);
}

type BpmnFactory = import('../modeling/BpmnFactory').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type ModdleCopy = import('./ModdleCopy').default;

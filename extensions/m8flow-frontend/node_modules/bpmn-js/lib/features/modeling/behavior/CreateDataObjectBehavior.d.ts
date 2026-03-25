/**
 * BPMN specific create data object behavior.
 *
 */
export default class CreateDataObjectBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param bpmnFactory
     */
    constructor(eventBus: EventBus, bpmnFactory: BpmnFactory);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnFactory = import('../BpmnFactory').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

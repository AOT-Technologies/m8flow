/**
 * This behavior makes sure we always set a fake
 * DataInputAssociation#targetRef as demanded by the BPMN 2.0
 * XSD schema.
 *
 * The reference is set to a bpmn:Property{ name: '__targetRef_placeholder' }
 * which is created on the fly and cleaned up afterwards if not needed
 * anymore.
 *
 */
export default class DataInputAssociationBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param bpmnFactory
     */
    constructor(eventBus: EventBus, bpmnFactory: BpmnFactory);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnFactory = import('../BpmnFactory').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

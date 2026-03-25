/**
 * Add referenced root elements (error, escalation, message, signal) if they don't exist.
 * Copy referenced root elements on copy & paste.
 *
 */
export default class RootElementReferenceBehavior extends CommandInterceptor {
    /**
     * @param bpmnjs
     * @param eventBus
     * @param injector
     * @param moddleCopy
     * @param bpmnFactory
     */
    constructor(bpmnjs: Modeler, eventBus: EventBus, injector: Injector, moddleCopy: ModdleCopy, bpmnFactory: BpmnFactory);
}

type Modeler = import('../../../Modeler').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type Injector = import('didi').Injector;
type ModdleCopy = import('../../copy-paste/ModdleCopy').default;
type BpmnFactory = import('../BpmnFactory').default;
type Element = import('../../../model/Types').Element;
type Shape = import('../../../model/Types').Shape;
type DirectionTRBL = import('diagram-js/lib/util/Types').DirectionTRBL;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

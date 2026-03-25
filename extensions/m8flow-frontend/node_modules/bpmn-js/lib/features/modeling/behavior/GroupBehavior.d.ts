/**
 * BPMN specific group behavior.
 *
 */
export default class GroupBehavior extends CommandInterceptor {
    /**
     * @param bpmnFactory
     * @param bpmnjs
     * @param elementRegistry
     * @param eventBus
     * @param injector
     * @param moddleCopy
     */
    constructor(bpmnFactory: BpmnFactory, bpmnjs: Modeler, elementRegistry: ElementRegistry, eventBus: EventBus, injector: Injector, moddleCopy: ModdleCopy);
}

type BpmnFactory = import('../BpmnFactory').default;
type Modeler = import('../../../Modeler').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type Injector = import('didi').Injector;
type ModdleCopy = import('../../copy-paste/ModdleCopy').default;
type Element = import('../../../model/Types').Element;
type Shape = import('../../../model/Types').Shape;
type DirectionTRBL = import('diagram-js/lib/util/Types').DirectionTRBL;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

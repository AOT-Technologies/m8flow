export default class ReplaceConnectionBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param modeling
     * @param bpmnRules
     * @param injector
     */
    constructor(eventBus: EventBus, modeling: Modeling, bpmnRules: BpmnRules, injector: Injector);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;
type BpmnRules = import('../../rules/BpmnRules').default;
type Injector = import('didi').Injector;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

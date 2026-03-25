export default class RemoveElementBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param bpmnRules
     * @param modeling
     */
    constructor(eventBus: EventBus, bpmnRules: BpmnRules, modeling: Modeling);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnRules = import('../../rules/BpmnRules').default;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

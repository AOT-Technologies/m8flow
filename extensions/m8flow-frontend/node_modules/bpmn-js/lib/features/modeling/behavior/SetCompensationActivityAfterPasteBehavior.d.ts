/**
 * A behavior that sets the property of Compensation Activity after paste operation
 *
 */
export default class SetCompensationActivityAfterPasteBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param modeling
     */
    constructor(eventBus: EventBus, modeling: Modeling);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnRules = import('../../rules/BpmnRules').default;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

/**
 * BPMN specific delete lane behavior.
 *
 */
export default class UpdateFlowNodeRefsBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param modeling
     */
    constructor(eventBus: EventBus, modeling: Modeling);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

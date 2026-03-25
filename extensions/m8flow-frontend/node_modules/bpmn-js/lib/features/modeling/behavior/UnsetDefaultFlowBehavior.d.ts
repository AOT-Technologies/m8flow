/**
 * A behavior that unsets the Default property of sequence flow source on
 * element delete, if the removed element is the Gateway or Task's default flow.
 *
 */
export default class DeleteSequenceFlowBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param modeling
     */
    constructor(eventBus: EventBus, modeling: Modeling);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

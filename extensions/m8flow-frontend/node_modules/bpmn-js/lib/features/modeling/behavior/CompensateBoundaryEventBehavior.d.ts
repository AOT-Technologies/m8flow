/**
 * Behavior ensuring that only a single compensation activity is connected to a
 * compensation boundary event when connecting, reconnecting or replacing shapes.
 *
 */
export default class CompensateBoundaryEventBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param modeling
     * @param bpmnRules
     */
    constructor(eventBus: import('diagram-js/lib/core/EventBus').default, modeling: import('../Modeling').default, bpmnRules: import('../../rules/BpmnRules').default);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
export type Modeling = any;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

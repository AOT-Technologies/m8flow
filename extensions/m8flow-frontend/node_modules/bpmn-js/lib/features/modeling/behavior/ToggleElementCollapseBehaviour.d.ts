export default class ToggleElementCollapseBehaviour extends CommandInterceptor {
    /**
     * @param eventBus
     * @param elementFactory
     * @param modeling
     */
    constructor(eventBus: EventBus, elementFactory: ElementFactory, modeling: Modeling);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type ElementFactory = import('../ElementFactory').default;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

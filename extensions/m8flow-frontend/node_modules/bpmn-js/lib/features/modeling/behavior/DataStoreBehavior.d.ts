/**
 * BPMN specific data store behavior.
 *
 */
export default class DataStoreBehavior extends CommandInterceptor {
    /**
     * @param canvas
     * @param commandStack
     * @param elementRegistry
     * @param eventBus
     */
    constructor(canvas: Canvas, commandStack: CommandStack, elementRegistry: ElementRegistry, eventBus: EventBus);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type CommandStack = import('diagram-js/lib/command/CommandStack').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

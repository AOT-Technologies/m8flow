export default class AppendBehavior extends CommandInterceptor {
    constructor(eventBus: any);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

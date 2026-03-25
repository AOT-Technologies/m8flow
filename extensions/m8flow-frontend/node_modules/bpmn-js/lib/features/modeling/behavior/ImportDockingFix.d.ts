/**
 * Fix broken dockings after DI imports.
 *
 */
export default class ImportDockingFix {
    static $inject: string[];
    /**
     * @param eventBus
     */
    constructor(eventBus: EventBus);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;

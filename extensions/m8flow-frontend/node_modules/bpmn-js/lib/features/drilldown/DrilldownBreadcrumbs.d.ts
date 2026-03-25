/**
 * Adds overlays that allow switching planes on collapsed subprocesses.
 *
 */
export default class DrilldownBreadcrumbs {
    static $inject: string[];
    /**
     * @param eventBus
     * @param elementRegistry
     * @param canvas
     */
    constructor(eventBus: EventBus, elementRegistry: ElementRegistry, canvas: Canvas);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type Element = import('../../model/Types').Element;
type Shape = import('../../model/Types').Shape;

/**
 * Correct hover targets in certain situations to improve diagram interaction.
 *
 */
export default class FixHoverBehavior {
    static $inject: string[];
    /**
     * @param elementRegistry
     * @param eventBus
     * @param canvas
     */
    constructor(elementRegistry: ElementRegistry, eventBus: EventBus, canvas: Canvas);
}

type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type Canvas = import('diagram-js/lib/core/Canvas').default;

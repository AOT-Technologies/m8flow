/**
 * Move collapsed subprocesses into view when drilling down.
 *
 * Zoom and scroll are saved in a session.
 *
 */
export default class DrilldownCentering {
    static $inject: string[];
    /**
     * @param eventBus
     * @param canvas
     */
    constructor(eventBus: EventBus, canvas: Canvas);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;

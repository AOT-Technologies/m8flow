/**
 * Snap during connect.
 *
 */
export default class BpmnConnectSnapping {
    static $inject: string[];
    /**
     * @param eventBus
     */
    constructor(eventBus: EventBus);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Event = import('diagram-js/lib/core/EventBus').Event;
type Shape = import('../../model/Types').Shape;
type Axis = import('diagram-js/lib/util/Types').Axis;
type Point = import('diagram-js/lib/util/Types').Point;

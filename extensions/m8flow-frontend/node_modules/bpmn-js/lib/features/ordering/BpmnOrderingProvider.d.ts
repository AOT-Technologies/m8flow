/**
 * A BPMN-specific ordering provider.
 *
 */
export default class BpmnOrderingProvider extends OrderingProvider {
    /**
     * @param eventBus
     * @param canvas
     */
    constructor(eventBus: EventBus, canvas: Canvas);
    getOrdering: (element: any, newParent: any) => {
        index: number;
        parent: any;
    };
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
import OrderingProvider from 'diagram-js/lib/features/ordering/OrderingProvider';

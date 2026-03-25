/**
 * BPMN-specific resize behavior.
 *
 */
export default class BpmnAutoResize extends AutoResize {
    /**
     * @param injector
     */
    constructor(injector: Injector);
    /**
     * Perform BPMN-specific resizing of participants.
     *
     * @param target
     * @param newBounds
     * @param hints
     */
    resize(target: Shape, newBounds: Rect, hints?: {
        autoResize?: string;
    }): void;
}

type Injector = import('didi').Injector;
type Shape = import('../../model/Types').Shape;
type Rect = import('diagram-js/lib/util/Types').Rect;
import AutoResize from 'diagram-js/lib/features/auto-resize/AutoResize';

export default class LabelEditingPreview {
    static $inject: string[];
    /**
     * @param eventBus
     * @param canvas
     * @param pathMap
     */
    constructor(eventBus: EventBus, canvas: Canvas, pathMap: PathMap);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type PathMap = import('../../draw/PathMap').default;

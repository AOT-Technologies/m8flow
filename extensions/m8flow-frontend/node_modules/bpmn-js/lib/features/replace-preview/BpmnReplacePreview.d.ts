export default class BpmnReplacePreview extends CommandInterceptor {
    /**
     * @param eventBus
     * @param elementRegistry
     * @param elementFactory
     * @param canvas
     * @param previewSupport
     */
    constructor(eventBus: EventBus, elementRegistry: ElementRegistry, elementFactory: ElementFactory, canvas: Canvas, previewSupport: PreviewSupport);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type ElementFactory = import('diagram-js/lib/core/ElementFactory').default;
type Canvas = import('diagram-js/lib/core/Canvas').default;
type PreviewSupport = import('diagram-js/lib/features/preview-support/PreviewSupport').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

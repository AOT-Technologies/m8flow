export default class LabelEditingProvider {
  static $inject: string[];

  /**
   * @param eventBus
   * @param bpmnFactory
   * @param canvas
   * @param directEditing
   * @param modeling
   * @param resizeHandles
   * @param textRenderer
   */
  constructor(eventBus: EventBus, bpmnFactory: BpmnFactory, canvas: Canvas, directEditing: any, modeling: Modeling, resizeHandles: ResizeHandles, textRenderer: TextRenderer);

  /**
   * Activate direct editing for activities and text annotations.
   *
   * @param element
   *
   * @return
   */
  activate(element: Element): {
      text: string;
      options?: {
          autoResize?: boolean;
          centerVertically?: boolean;
          resizable?: boolean;
      };
  } & DirectEditingContext;

  /**
   * Get the editing bounding box based on the element's size and position.
   *
   * @param element
   *
   * @return
   */
  getEditingBBox(element: Element): DirectEditingContext;

  update(element: any, newLabel: any, activeContextText: any, bounds: any): void;
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnFactory = import('../modeling/BpmnFactory').default;
type Canvas = import('diagram-js/lib/core/Canvas').default;
export type DirectEditing = any;
type Modeling = import('../modeling/Modeling').default;
type ResizeHandles = import('diagram-js/lib/features/resize/ResizeHandles').default;
type TextRenderer = import('../../draw/TextRenderer').default;
type Element = import('../../model/Types').Element;

export type DirectEditingContext = {
    bounds: {
        x: number;
        y: number;
        width: number;
        height: number;
        minWidth?: number;
        minHeight?: number;
    };
    style: any;
};

/**
 * An importer that adds bpmn elements to the canvas
 *
 */
export default class BpmnImporter {
  static $inject: string[];

  /**
   * @param eventBus
   * @param canvas
   * @param elementFactory
   * @param elementRegistry
   * @param textRenderer
   */
  constructor(eventBus: EventBus, canvas: Canvas, elementFactory: ElementFactory, elementRegistry: ElementRegistry, textRenderer: TextRenderer);

  /**
   * Add a BPMN element (semantic) to the canvas making it a child of the
   * given parent.
   *
   * @param semantic
   * @param di
   * @param parentElement
   *
   * @return
   */
  add(semantic: ModdleElement, di: ModdleElement, parentElement: Shape): Shape | Root | Connection;

  /**
   * Add a label to a given element.
   *
   * @param semantic
   * @param di
   * @param element
   *
   * @return
   */
  addLabel(semantic: ModdleElement, di: ModdleElement, element: Element): Label;
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type ElementFactory = import('../features/modeling/ElementFactory').default;
type TextRenderer = import('../draw/TextRenderer').default;
type Element = import('../model/Types').Element;
type Label = import('../model/Types').Label;
type Shape = import('../model/Types').Shape;
type Connection = import('../model/Types').Connection;
type Root = import('../model/Types').Root;
type ModdleElement = import('../model/Types').ModdleElement;

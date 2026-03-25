/**
 * A BPMN-specific element factory.
 *
 *
 * @extends {BaseElementFactory<T, U, V, W>}
 *
 */
export default class ElementFactory<T extends import("../../model/Types").Connection = import("../../model/Types").Connection, U extends import("../../model/Types").Label = import("../../model/Types").Label, V extends import("../../model/Types").Root = import("../../model/Types").Root, W extends import("../../model/Types").Shape = import("../../model/Types").Shape> extends BaseElementFactory<T, U, V, W> {
  static $inject: string[];

  /**
   * @param bpmnFactory
   * @param moddle
   */
  constructor(bpmnFactory: BpmnFactory, moddle: Moddle);

  /**
   * Create a label.
   *
   * @param elementType
   * @param attrs
   * @return
   */
  create(elementType: 'label', attrs?: Partial<Label> & Partial<BpmnAttributes>): U;

  /**
   * Create a connection.
   *
   * @param elementType
   * @param attrs
   * @return
   */
  create(
    elementType: 'connection',
    attrs?: Partial<Connection> & Partial<BpmnAttributes>
  ): T;

  /**
   * Create a shape.
   *
   * @param elementType
   * @param attrs
   * @return
   */
  create(elementType: 'shape', attrs?: Partial<Shape> & Partial<BpmnAttributes>): W;

  /**
   * Create a root element.
   *
   * @param elementType
   * @param attrs
   * @return
   */
  create(elementType: 'root', attrs?: Partial<Root> & Partial<BpmnAttributes>): V;

  /**
   * Create a BPMN connection.
   *
   * @param elementType
   * @param attrs
   * @return
   */
  createElement(
    elementType: 'connection',
    attrs?: Partial<Connection> & Partial<BpmnAttributes>
  ): T;

  /**
   * Create a BPMN shape.
   *
   * @param elementType
   * @param attrs
   * @return
   */
  createElement(elementType: 'shape', attrs?: Partial<Shape> & Partial<BpmnAttributes>): W;

  /**
   * Create a BPMN root element.
   *
   * @param elementType
   * @param attrs
   * @return
   */
  createElement(elementType: 'root', attrs?: Partial<Root> & Partial<BpmnAttributes>): V;

  /**
   * Get the default size of a diagram element.
   *
   * @param element The element.
   * @param di The DI.
   *
   * @return Default width and height of the element.
   */
  getDefaultSize(element: Element, di: ModdleElement): Dimensions;

  /**
   * Create participant.
   *
   * @param attrs
   * Attributes or whether the participant is expanded.
   *
   * @return The created participant.
   */
  createParticipantShape(attrs?: boolean | (Partial<Shape> & Partial<BpmnAttributes>)): W;
}

type Dimensions = import('diagram-js/lib/util/Types').Dimensions;
type BpmnFactory = import('./BpmnFactory').default;
type BpmnAttributes = import('../../model/Types').BpmnAttributes;
type Connection = import('../../model/Types').Connection;
type Element = import('../../model/Types').Element;
type Label = import('../../model/Types').Label;
type Root = import('../../model/Types').Root;
type Shape = import('../../model/Types').Shape;
type Moddle = import('../../model/Types').Moddle;
type ModdleElement = import('../../model/Types').ModdleElement;
import BaseElementFactory from 'diagram-js/lib/core/ElementFactory';

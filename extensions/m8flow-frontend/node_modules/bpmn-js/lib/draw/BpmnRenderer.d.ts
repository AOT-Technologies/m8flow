/**
 * A renderer for BPMN elements
 *
 */
export default class BpmnRenderer extends BaseRenderer {
  static $inject: string[];

  /**
   * @param config
   * @param eventBus
   * @param styles
   * @param pathMap
   * @param canvas
   * @param textRenderer
   * @param priority
   */
  constructor(config: BpmnRendererConfig, eventBus: import('diagram-js/lib/core/EventBus').default, styles: import('diagram-js/lib/draw/Styles').default, pathMap: import('./PathMap').default, canvas: import('diagram-js/lib/core/Canvas').default, textRenderer: import('./TextRenderer').default, priority?: number);

  handlers: {
      'bpmn:AdHocSubProcess': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:Association': (parentGfx: any, element: any, attrs?: {}) => SVGElement;
      'bpmn:BoundaryEvent': (parentGfx: any, element: any, attrs?: {}) => SVGCircleElement;
      'bpmn:BusinessRuleTask': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:CallActivity': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:ComplexGateway': (parentGfx: any, element: any, attrs?: {}) => SVGPolygonElement;
      'bpmn:DataInput': (parentGfx: any, element: any, attrs?: {}) => SVGPathElement;
      'bpmn:DataInputAssociation': (parentGfx: any, element: any, attrs?: {}) => SVGElement;
      'bpmn:DataObject': (parentGfx: any, element: any, attrs?: {}) => SVGPathElement;
      'bpmn:DataObjectReference': (parentGfx: any, element: any, attrs: any) => any;
      'bpmn:DataOutput': (parentGfx: any, element: any, attrs?: {}) => SVGPathElement;
      'bpmn:DataOutputAssociation': (parentGfx: any, element: any, attrs?: {}) => SVGElement;
      'bpmn:DataStoreReference': (parentGfx: any, element: any, attrs?: {}) => SVGPathElement;
      'bpmn:EndEvent': (parentGfx: any, element: any, attrs?: {}) => SVGCircleElement;
      'bpmn:EventBasedGateway': (parentGfx: any, element: any, attrs?: {}) => SVGPolygonElement;
      'bpmn:ExclusiveGateway': (parentGfx: any, element: any, attrs?: {}) => SVGPolygonElement;
      'bpmn:Gateway': (parentGfx: any, element: any, attrs?: {}) => SVGPolygonElement;
      'bpmn:Group': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:InclusiveGateway': (parentGfx: any, element: any, attrs?: {}) => SVGPolygonElement;
      'bpmn:IntermediateEvent': (parentGfx: any, element: any, attrs?: {}) => SVGCircleElement;
      'bpmn:IntermediateCatchEvent': (parentGfx: any, element: any, attrs: any) => any;
      'bpmn:IntermediateThrowEvent': (parentGfx: any, element: any, attrs: any) => any;
      'bpmn:Lane': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:ManualTask': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:MessageFlow': (parentGfx: any, element: any, attrs?: {}) => SVGElement;
      'bpmn:ParallelGateway': (parentGfx: any, element: any, attrs?: {}) => SVGPolygonElement;
      'bpmn:Participant': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:ReceiveTask': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:ScriptTask': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:SendTask': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:SequenceFlow': (parentGfx: any, element: any, attrs?: {}) => SVGElement;
      'bpmn:ServiceTask': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:StartEvent': (parentGfx: any, element: any, attrs?: {}) => SVGCircleElement;
      'bpmn:SubProcess': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:Task': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:TextAnnotation': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:Transaction': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      'bpmn:UserTask': (parentGfx: any, element: any, attrs?: {}) => SVGRectElement;
      label: (parentGfx: any, element: any, attrs?: {}) => SVGElement;
  };

  /**
   * @param element
   *
   * @return
   */
  canRender(element: Element): boolean;

  /**
   * Draw shape into parentGfx.
   *
   * @param parentGfx
   * @param shape
   * @param attrs
   *
   * @return mainGfx
   */
  drawShape(parentGfx: SVGElement, shape: Shape, attrs?: Attrs): SVGElement;

  /**
   * Draw connection into parentGfx.
   *
   * @param parentGfx
   * @param connection
   * @param attrs
   *
   * @return mainGfx
   */
  drawConnection(parentGfx: SVGElement, connection: Connection, attrs?: Attrs): SVGElement;

  /**
   * Get shape path.
   *
   * @param shape
   *
   * @return path
   */
  getShapePath(shape: Shape): string;
}

export type BpmnRendererConfig = Partial<{
    defaultFillColor: string;
    defaultStrokeColor: string;
    defaultLabelColor: string;
}>;

export type Attrs = Partial<{
    fill: string;
    stroke: string;
    width: string;
    height: string;
}>;

type Element = import('../model/Types').Element;
type Shape = import('../model/Types').Shape;
type Connection = import('../model/Types').Connection;
import BaseRenderer from 'diagram-js/lib/draw/BaseRenderer';

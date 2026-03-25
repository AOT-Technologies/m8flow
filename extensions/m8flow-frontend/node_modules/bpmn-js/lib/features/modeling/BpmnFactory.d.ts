/**
 * A factory for BPMN elements.
 *
 */
export default class BpmnFactory {
  static $inject: string[];

  /**
   * @param moddle
   */
  constructor(moddle: Moddle);

  /**
   * Create BPMN element.
   *
   * @param type
   * @param attrs
   *
   * @return
   */
  create(type: string, attrs?: any): ModdleElement;

  /**
   * @return
   */
  createDiLabel(): ModdleElement;

  /**
   * @param semantic
   * @param attrs
   * @return
   */
  createDiShape(semantic: ModdleElement, attrs?: any): ModdleElement;

  /**
   * @return
   */
  createDiBounds(bounds: any): ModdleElement;

  /**
   * @param waypoints
   *
   * @return
   */
  createDiWaypoints(waypoints: Point[]): ModdleElement[];

  /**
   * @param point
   *
   * @return
   */
  createDiWaypoint(point: Point): ModdleElement;

  /**
   * @param semantic
   * @param attrs
   *
   * @return
   */
  createDiEdge(semantic: ModdleElement, attrs?: any): ModdleElement;

  /**
   * @param semantic
   * @param attrs
   *
   * @return
   */
  createDiPlane(semantic: ModdleElement, attrs?: any): ModdleElement;
}

type Moddle = import('../../model/Types').Moddle;
type ModdleElement = import('../../model/Types').ModdleElement;
type Point = import('diagram-js/lib/util/Types').Point;

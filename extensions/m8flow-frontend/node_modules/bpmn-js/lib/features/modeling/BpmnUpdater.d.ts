/**
 * A handler responsible for updating the underlying BPMN 2.0 XML & DI
 * once changes on the diagram happen.
 *
 */
export default class BpmnUpdater extends CommandInterceptor {
  /**
   * @param eventBus
   * @param bpmnFactory
   * @param connectionDocking
   */
  constructor(eventBus: EventBus, bpmnFactory: BpmnFactory, connectionDocking: CroppingConnectionDocking);

  /**
   * @param context
   */
  updateAttachment(context: {
      shape: Shape;
      host: Shape;
  }): void;

  /**
   * @param element
   * @param oldParent
   */
  updateParent(element: Element, oldParent: Parent): void;

  /**
   * @param shape
   */
  updateBounds(shape: Shape): void;

  /**
   * @param businessObject
   * @param newContainment
   * @param oldContainment
   */
  updateFlowNodeRefs(businessObject: ModdleElement, newContainment: ModdleElement, oldContainment: ModdleElement): void;

  /**
   * @param connection
   * @param newSource
   * @param newTarget
   */
  updateDiConnection(connection: Connection, newSource: Element, newTarget: Element): void;

  /**
   * @param di
   * @param parentDi
   */
  updateDiParent(di: ModdleElement, parentDi: ModdleElement): void;

  /**
   * @param container
   *
   * @return
   */
  getLaneSet(container: ModdleElement): ModdleElement;

  /**
   * @param businessObject
   * @param newParent
   * @param visualParent
   */
  updateSemanticParent(businessObject: ModdleElement, newParent: ModdleElement, visualParent: ModdleElement): void;

  /**
   * @param connection
   */
  updateConnectionWaypoints(connection: Connection): void;

  /**
   * @param context
   */
  updateConnection(context: {
      connection: Connection;
      parent: Parent;
      newParent: Parent;
  }): void;
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnFactory = import('./BpmnFactory').default;
type CroppingConnectionDocking = import('diagram-js/lib/layout/CroppingConnectionDocking').default;
type Connection = import('../../model/Types').Connection;
type Element = import('../../model/Types').Element;
type Shape = import('../../model/Types').Shape;
type Parent = import('../../model/Types').Parent;
type ModdleElement = import('../../model/Types').ModdleElement;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

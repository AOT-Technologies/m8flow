/**
 * Creates bpmndi:BPMNPlane elements and canvas planes when collapsed subprocesses are created.
 *
 */
export default class SubProcessPlaneBehavior extends CommandInterceptor {
  /**
   * @param canvas
   * @param eventBus
   * @param modeling
   * @param elementFactory
   * @param bpmnFactory
   * @param bpmnjs
   * @param elementRegistry
   */
  constructor(canvas: Canvas, eventBus: EventBus, modeling: Modeling, elementFactory: ElementFactory, bpmnFactory: BpmnFactory, bpmnjs: Modeler, elementRegistry: ElementRegistry);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;
type ElementFactory = import('../ElementFactory').default;
type BpmnFactory = import('../BpmnFactory').default;
type Modeler = import('../../../Modeler').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type Element = import('../../../model/Types').Element;
type Root = import('../../../model/Types').Root;
type ModdleElement = import('../../../model/Types').ModdleElement;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

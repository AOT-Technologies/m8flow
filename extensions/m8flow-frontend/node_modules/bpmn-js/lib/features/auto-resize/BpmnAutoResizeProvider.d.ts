/**
 * BPMN-specific provider for automatic resizung.
 *
 */
export default class BpmnAutoResizeProvider extends AutoResizeProvider {
  /**
   * @param eventBus
   * @param modeling
   */
  constructor(eventBus: EventBus, modeling: Modeling);

  /**
   * BPMN-specific check whether given elements can be resized.
   *
   * @param elements
   * @param target
   *
   * @return
   */
  canResize(elements: Shape[], target: Shape): boolean;
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../modeling/Modeling').default;
type Shape = import('../../model/Types').Shape;
import AutoResizeProvider from 'diagram-js/lib/features/auto-resize/AutoResizeProvider';

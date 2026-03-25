/**
 * A preview for appending.
 *
 */
export default class AppendPreview {
  static $inject: string[];

  /**
   * @param complexPreview
   * @param connectionDocking
   * @param elementFactory
   * @param eventBus
   * @param layouter
   * @param rules
   */
  constructor(complexPreview: ComplexPreview, connectionDocking: ConnectionDocking, elementFactory: ElementFactory, eventBus: EventBus, layouter: BpmnLayouter, rules: Rules);

  /**
   * Create a preview of appending a shape of the given type to the given source.
   *
   * @param source
   * @param type
   * @param options
   */
  create(source: Shape, type: string, options: Partial<Shape>): void;

  cleanUp(): void;
}

type ComplexPreview = import('diagram-js/lib/features/complex-preview/ComplexPreview').default;
type ConnectionDocking = import('diagram-js/lib/layout/ConnectionDocking').default;
type ElementFactory = import('../modeling/ElementFactory').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type BpmnLayouter = import('../modeling/BpmnLayouter').default;
type Rules = import('diagram-js/lib/features/rules/Rules').default;
type Shape = import('../../model/Types').Shape;

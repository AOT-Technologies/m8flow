/**
 * BPMN-specific hit zones and interaction fixes.
 *
 */
export default class BpmnInteractionEvents {
  static $inject: string[];

  /**
   * @param eventBus
   * @param interactionEvents
   */
  constructor(eventBus: EventBus, interactionEvents: InteractionEvents);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type InteractionEvents = import('diagram-js/lib/features/interaction-events/InteractionEvents').default;
type Element = import('../../model/Types').Element;
type Shape = import('../../model/Types').Shape;

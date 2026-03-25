export default class DrilldownOverlayBehavior extends CommandInterceptor {
  /**
   * @param canvas
   * @param eventBus
   * @param elementRegistry
   * @param overlays
   * @param translate
   */
  constructor(canvas: Canvas, eventBus: EventBus, elementRegistry: ElementRegistry, overlays: Overlays, translate: Translate);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type Overlays = import('diagram-js/lib/features/overlays/Overlays').default;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
type Element = import('../../model/Types').Element;
type Parent = import('../../model/Types').Parent;
type Shape = import('../../model/Types').Shape;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

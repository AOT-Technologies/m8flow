/**
 * Hook into `import.render.start` and create new planes for diagrams with
 * collapsed subprocesses and all DI elements on the same plane.
 *
 */
export default class SubprocessCompatibility {
  static $inject: string[];

  /**
   * @param eventBus
   * @param moddle
   */
  constructor(eventBus: EventBus, moddle: Moddle);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Moddle = import('../../model/Types').Moddle;
type Element = import('../../model/Types').Element;
type Shape = import('../../model/Types').Shape;
type CanvasPlane = import('diagram-js/lib/core/Canvas').CanvasPlane;
type Rect = import('diagram-js/lib/util/Types').Rect;

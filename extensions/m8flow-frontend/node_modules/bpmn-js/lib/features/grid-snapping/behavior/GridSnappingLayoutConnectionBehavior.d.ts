/**
 * Snaps connections with Manhattan layout.
 *
 */
export default class GridSnappingLayoutConnectionBehavior extends CommandInterceptor {
  /**
   * @param eventBus
   * @param gridSnapping
   * @param modeling
   */
  constructor(eventBus: EventBus, gridSnapping: GridSnapping, modeling: Modeling);

  /**
   * Snap middle segments of a given connection.
   *
   * @param waypoints
   *
   * @return
   */
  snapMiddleSegments(waypoints: Point[]): Point[];
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type GridSnapping = import('diagram-js/lib/features/grid-snapping/GridSnapping').default;
type Modeling = import('../../modeling/Modeling').default;
type Point = import('diagram-js/lib/util/Types').Point;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

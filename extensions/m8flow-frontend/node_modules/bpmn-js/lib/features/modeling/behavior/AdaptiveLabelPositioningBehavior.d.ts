/**
 * A component that makes sure that external labels are added
 * together with respective elements and properly updated (DI wise)
 * during move.
 *
 */
export default class AdaptiveLabelPositioningBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param modeling
     */
    constructor(eventBus: EventBus, modeling: Modeling);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;
type Element = import('../../../model/Types').Element;
type Shape = import('../../../model/Types').Shape;
type DirectionTRBL = import('diagram-js/lib/util/Types').DirectionTRBL;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

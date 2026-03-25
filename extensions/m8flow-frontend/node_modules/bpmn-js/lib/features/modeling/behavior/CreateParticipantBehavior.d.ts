export const PARTICIPANT_BORDER_WIDTH: number;

/**
 * BPMN-specific behavior for creating participants.
 *
 */
export default class CreateParticipantBehavior extends CommandInterceptor {
    /**
     * @param canvas
     * @param eventBus
     * @param modeling
     */
    constructor(canvas: Canvas, eventBus: EventBus, modeling: Modeling);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type EventBus = import('diagram-js/lib/core/EventBus').default;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

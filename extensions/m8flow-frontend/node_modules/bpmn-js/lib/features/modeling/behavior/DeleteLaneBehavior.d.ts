/**
 * BPMN specific delete lane behavior.
 *
 */
export default class DeleteLaneBehavior extends CommandInterceptor {
    /**
     * @param eventBus
     * @param spaceTool
     */
    constructor(eventBus: EventBus, spaceTool: SpaceTool);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type SpaceTool = import('../../space-tool/BpmnSpaceTool').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

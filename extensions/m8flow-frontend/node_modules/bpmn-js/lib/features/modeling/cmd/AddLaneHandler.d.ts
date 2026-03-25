/**
 * A handler that allows us to add a new lane
 * above or below an existing one.
 *
 * @implements {CommandHandler}
 *
 */
export default class AddLaneHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param modeling
   * @param spaceTool
   */
  constructor(modeling: Modeling, spaceTool: SpaceTool);

  preExecute(context: any): void;
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type Modeling = import('../Modeling').default;
type SpaceTool = import('../../space-tool/BpmnSpaceTool').default;

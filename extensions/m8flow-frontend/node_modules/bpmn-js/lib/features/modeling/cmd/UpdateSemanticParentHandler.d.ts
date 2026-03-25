/**
 * @implements {CommandHandler}
 *
 */
export default class UpdateSemanticParentHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param bpmnUpdater
   */
  constructor(bpmnUpdater: BpmnUpdater);

  execute(context: any): any[];
  revert(context: any): any[];
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type BpmnUpdater = import('../BpmnUpdater').default;

/**
 * @implements {CommandHandler}
 *
 */
export default class SetColorHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param commandStack
   */
  constructor(commandStack: CommandStack);

  postExecute(context: any): void;
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type CommandStack = import('diagram-js/lib/command/CommandStack').default;
type ModdleElement = import('../../../model/Types').ModdleElement;

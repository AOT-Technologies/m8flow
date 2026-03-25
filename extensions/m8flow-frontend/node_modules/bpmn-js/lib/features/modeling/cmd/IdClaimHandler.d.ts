/**
 * @implements {CommandHandler}
 *
 */
export default class IdClaimHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param moddle
   */
  constructor(moddle: Moddle);

  execute(context: any): any[];

  /**
   * Command revert implementation.
   */
  revert(context: any): any[];
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type Moddle = import('../../../model/Types').Moddle;

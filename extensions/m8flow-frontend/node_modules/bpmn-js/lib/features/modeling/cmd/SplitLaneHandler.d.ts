/**
 * A handler that splits a lane into a number of sub-lanes,
 * creating new sub lanes, if necessary.
 *
 * @implements {CommandHandler}
 *
 */
export default class SplitLaneHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param modeling
   */
  constructor(modeling: Modeling);

  preExecute(context: any): void;
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type Modeling = import('../Modeling').default;

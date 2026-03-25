/**
 * A handler that updates lane refs on changed elements.
 *
 * @implements {CommandHandler}
 *
 */
export default class UpdateFlowNodeRefsHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param elementRegistry
   */
  constructor(elementRegistry: ElementRegistry);

  execute(context: any): any[];
  revert(context: any): any[];
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type Shape = import('../../../model/Types').Shape;

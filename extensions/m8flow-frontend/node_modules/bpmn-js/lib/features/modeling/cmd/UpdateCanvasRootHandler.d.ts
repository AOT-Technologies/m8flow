/**
 * @implements {CommandHandler}
 *
 */
export default class UpdateCanvasRootHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param canvas
   * @param modeling
   */
  constructor(canvas: Canvas, modeling: Modeling);

  execute(context: any): any[];
  revert(context: any): any[];
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type Canvas = import('diagram-js/lib/core/Canvas').default;
type Modeling = import('../Modeling').default;

/**
 * A handler that resizes a lane.
 *
 * @implements {CommandHandler}
 *
 */
export default class ResizeLaneHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param modeling
   * @param spaceTool
   */
  constructor(modeling: Modeling, spaceTool: SpaceTool);

  preExecute(context: any): void;

  /**
   * Resize balanced, adjusting next / previous lane sizes.
   *
   * @param shape
   * @param newBounds
   */
  resizeBalanced(shape: Shape, newBounds: Rect): void;

  /**
   * Resize, making actual space and moving below / above elements.
   *
   * @param shape
   * @param newBounds
   */
  resizeSpace(shape: Shape, newBounds: Rect): void;
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type Modeling = import('../Modeling').default;
type SpaceTool = import('../../space-tool/BpmnSpaceTool').default;
type Shape = import('../../../model/Types').Shape;
type Rect = import('diagram-js/lib/util/Types').Rect;

/**
 * A handler that implements a BPMN 2.0 property update.
 *
 * This should be used to set simple properties on elements with
 * an underlying BPMN business object.
 *
 * Use respective diagram-js provided handlers if you would
 * like to perform automated modeling.
 *
 * @implements {CommandHandler}
 *
 */
export default class UpdatePropertiesHandler implements CommandHandler {
  static $inject: string[];

  /**
   * @param elementRegistry
   * @param moddle
   * @param modeling
   * @param textRenderer
   */
  constructor(elementRegistry: ElementRegistry, moddle: Moddle, modeling: Modeling, textRenderer: TextRenderer);

  /**
   * Update a BPMN element's properties.
   *
   * @param context
   *
   * @return
   */
  execute(context: {
      element: Element;
      properties: Record<string, any>;
  } & CommandContext): Element[];

  postExecute(context: any): void;

  /**
   * Revert updating a BPMN element's properties.
   *
   * @param context
   *
   * @return
   */
  revert(context: {
      element: Element;
      properties: Record<string, any>;
      oldProperties: Record<string, any>;
  } & CommandContext): Element[];
}

type CommandHandler = import('diagram-js/lib/command/CommandHandler').default;
type CommandContext = import('diagram-js/lib/command/CommandStack').CommandContext;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type Moddle = import('../../../model/Types').Moddle;
type Modeling = import('../Modeling').default;
type TextRenderer = import('../../../draw/TextRenderer').default;
type Element = import('../../../model/Types').Element;

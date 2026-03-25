/**
 * BPMN-specific outline provider.
 *
 * @implements {BaseOutlineProvider}
 *
 */
export default class OutlineProvider implements BaseOutlineProvider {
  static $inject: string[];

  /**
   * @param outline
   * @param styles
   */
  constructor(outline: Outline, styles: Styles);

  /**
   * Returns outline for a given element.
   *
   * @param element
   *
   * @return
   */
  getOutline(element: Element): Outline;

  /**
   * Updates the outline for a given element.
   * Returns true if the update for the given element was handled by this provider.
   *
   * @param element
   * @param outline
   * @returns
   */
  updateOutline(element: Element, outline: Outline): boolean;
}

type BaseOutlineProvider = import('diagram-js/lib/features/outline/OutlineProvider').default;
type Outline = import('diagram-js/lib/features/outline/OutlineProvider').Outline;
type Styles = import('diagram-js/lib/draw/Styles').default;
type Element = import('diagram-js/lib/model/Types').Element;

/**
 * Provides ability to search for BPMN elements.
 *
 * @implements {SearchPadProvider}
 *
 */
export default class BpmnSearchProvider implements SearchPadProvider {
  static $inject: string[];

  /**
   * @param elementRegistry
   * @param searchPad
   * @param canvas
   */
  constructor(elementRegistry: ElementRegistry, searchPad: SearchPad, canvas: Canvas);

  /**
   * @param pattern
   *
   * @return
   */
  find(pattern: string): SearchResult[];
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type SearchPad = import('diagram-js/lib/features/search-pad/SearchPad').default;
type SearchPadProvider = import('diagram-js/lib/features/search-pad/SearchPadProvider').default;
type SearchResult = import('diagram-js/lib/features/search-pad/SearchPadProvider').SearchResult;

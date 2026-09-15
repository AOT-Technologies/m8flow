/** Shared imperative handle BpmnCanvas, DmnCanvas, TextFileCanvas, and
 * FormSchemaCanvas expose,
 * so the page-level Download/Save controls can pull the current file contents
 * and manage dirty-tracking without any canvas needing to know about
 * downloading or the save API. */

/** Opaque clean-marker captured at export time. BPMN/DMN use commandStack
 * index; text uses the exported string; form schema uses the three companions. */
export type SaveBaseline =
  | number
  | string
  | { schema: string; ui: string; example: string };

export type SaveSnapshot = {
  xml: string;
  baseline: SaveBaseline;
};

export type DiagramCanvasHandle = {
  /** Export current content and capture the dirty-tracking baseline for that
   * snapshot (before any further edits). Pass `baseline` to `markSaved` after
   * a successful PUT so in-flight edits are not marked clean. */
  saveXML: () => Promise<SaveSnapshot>;
  /** Baselined against the snapshot that was saved, not live state. Returns
   * whether the canvas is still dirty relative to that baseline. */
  markSaved: (baseline: SaveBaseline) => boolean;
};

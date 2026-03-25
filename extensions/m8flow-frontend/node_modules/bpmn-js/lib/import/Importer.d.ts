/**
 * Import the definitions into a diagram.
 *
 * Errors and warnings are reported through the specified callback.
 *
 * @param diagram
 * @param definitions
 * @param bpmnDiagram The diagram to be rendered (if not
 * provided, the first one will be rendered).
 *
 * @return
 */
export function importBpmnDiagram(
  diagram: ModdleElement,
  definitions: ModdleElement,
  bpmnDiagram?: ModdleElement
): Promise<ImportBPMNDiagramResult>;

type ModdleElement = import('../model/Types').ModdleElement;

export type ImportBPMNDiagramResult = {
    warnings: string[];
};

export type ImportBPMNDiagramError = ImportBPMNDiagramResult & Error;

/**
 * A palette provider for BPMN 2.0 elements.
 *
 */
export default class PaletteProvider {
  static $inject: string[];

  /**
   * @param palette
   * @param create
   * @param elementFactory
   * @param spaceTool
   * @param lassoTool
   * @param handTool
   * @param globalConnect
   * @param translate
   */
  constructor(palette: Palette, create: Create, elementFactory: ElementFactory, spaceTool: SpaceTool, lassoTool: LassoTool, handTool: HandTool, globalConnect: GlobalConnect, translate: Translate);

  /**
   * @return
   */
  getPaletteEntries(): PaletteEntries;
}

type Palette = import('diagram-js/lib/features/palette/Palette').default;
type Create = import('diagram-js/lib/features/create/Create').default;
type ElementFactory = import('diagram-js/lib/core/ElementFactory').default;
type SpaceTool = import('../space-tool/BpmnSpaceTool').default;
type LassoTool = import('diagram-js/lib/features/lasso-tool/LassoTool').default;
type HandTool = import('diagram-js/lib/features/hand-tool/HandTool').default;
type GlobalConnect = import('diagram-js/lib/features/global-connect/GlobalConnect').default;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
type PaletteEntries = import('diagram-js/lib/features/palette/Palette').PaletteEntries;

declare namespace _default {
    const __depends__: (import("didi").ModuleDeclaration | {
      spaceTool: (string | typeof import("../space-tool/BpmnSpaceTool").default)[];
    })[];
    const __init__: string[];
    const paletteProvider: (string | typeof PaletteProvider)[];
}
export default _default;
import PaletteProvider from './PaletteProvider';

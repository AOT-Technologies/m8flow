declare namespace _default {
    const __depends__: (import("didi").ModuleDeclaration | {
      bpmnReplace: (string | typeof import("../replace/BpmnReplace").default)[];
    } | {
      bpmnAutoPlace: (string | typeof import("../auto-place/BpmnAutoPlace").default)[];
    })[];
    const __init__: string[];
    const replaceMenuProvider: (string | typeof ReplaceMenuProvider)[];
}
export default _default;
import ReplaceMenuProvider from './ReplaceMenuProvider';

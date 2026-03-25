declare namespace _default {
    const __depends__: (import("didi").ModuleDeclaration | {
      bpmnCopyPaste: (string | typeof import("../copy-paste/BpmnCopyPaste").default)[];
      moddleCopy: (string | typeof import("../copy-paste/ModdleCopy").default)[];
    })[];
    const bpmnReplace: (string | typeof BpmnReplace)[];
}
export default _default;
import BpmnReplace from './BpmnReplace';

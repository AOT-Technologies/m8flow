declare namespace _default {
    const __depends__: (import("didi").ModuleDeclaration | {
      bpmnAutoPlace: (string | typeof import("../auto-place/BpmnAutoPlace").default)[];
    } | {
      bpmnFactory: (string | typeof import("../modeling/BpmnFactory").default)[];
      bpmnUpdater: (string | typeof import("../modeling/BpmnUpdater").default)[];
      elementFactory: (string | typeof import("../modeling/ElementFactory").default)[];
      modeling: (string | typeof import("../modeling/Modeling").default)[];
      layouter: (string | typeof import("../modeling/BpmnLayouter").default)[];
      connectionDocking: (string | typeof import("diagram-js/lib/layout/CroppingConnectionDocking").default)[];
    })[];
    const __init__: string[];
    const appendPreview: (string | typeof AppendPreview)[];
}
export default _default;
import AppendPreview from './AppendPreview';

declare namespace _default {
    const __init__: string[];
    const __depends__: (import("didi").ModuleDeclaration | {
      bpmnRules: (string | typeof import("../rules/BpmnRules").default)[];
    } | {
      bpmnDiOrdering: (string | typeof import("../di-ordering/BpmnDiOrdering").default)[];
    } | {
      bpmnOrderingProvider: (string | typeof import("../ordering/BpmnOrderingProvider").default)[];
    } | {
      bpmnReplace: (string | typeof import("../replace/BpmnReplace").default)[];
    } | {
      spaceTool: (string | typeof import("../space-tool/BpmnSpaceTool").default)[];
    })[];
    const bpmnFactory: (string | typeof BpmnFactory)[];
    const bpmnUpdater: (string | typeof BpmnUpdater)[];
    const elementFactory: (string | typeof ElementFactory)[];
    const modeling: (string | typeof Modeling)[];
    const layouter: (string | typeof BpmnLayouter)[];
    const connectionDocking: (string | typeof CroppingConnectionDocking)[];
}
export default _default;
import BpmnFactory from './BpmnFactory';
import BpmnUpdater from './BpmnUpdater';
import ElementFactory from './ElementFactory';
import Modeling from './Modeling';
import BpmnLayouter from './BpmnLayouter';
import CroppingConnectionDocking from 'diagram-js/lib/layout/CroppingConnectionDocking';

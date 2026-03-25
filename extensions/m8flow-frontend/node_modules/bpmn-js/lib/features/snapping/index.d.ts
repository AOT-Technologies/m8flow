declare namespace _default {
    const __depends__: import("didi").ModuleDeclaration[];
    const __init__: string[];
    const connectSnapping: (string | typeof BpmnConnectSnapping)[];
    const createMoveSnapping: (string | typeof BpmnCreateMoveSnapping)[];
}
export default _default;
import BpmnConnectSnapping from './BpmnConnectSnapping';
import BpmnCreateMoveSnapping from './BpmnCreateMoveSnapping';

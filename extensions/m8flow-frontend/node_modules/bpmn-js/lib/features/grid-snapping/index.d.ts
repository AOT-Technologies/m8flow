declare namespace _default {
    const __depends__: (import("didi").ModuleDeclaration | {
      gridSnappingAutoPlaceBehavior: (string | typeof import("./behavior/GridSnappingAutoPlaceBehavior").default)[];
      gridSnappingParticipantBehavior: (string | typeof import("./behavior/GridSnappingParticipantBehavior").default)[];
      gridSnappingLayoutConnectionBehavior: (string | typeof import("./behavior/GridSnappingLayoutConnectionBehavior").default)[];
    })[];
    const __init__: string[];
    const bpmnGridSnapping: (string | typeof BpmnGridSnapping)[];
}
export default _default;
import BpmnGridSnapping from './BpmnGridSnapping';

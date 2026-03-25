declare namespace _default {
    const __depends__: ({
      bpmnRenderer: (string | typeof import("../draw/BpmnRenderer").default)[];
      textRenderer: (string | typeof import("../draw/TextRenderer").default)[];
      pathMap: (string | typeof import("../draw/PathMap").default)[];
    } | {
      bpmnImporter: (string | typeof import("../import/BpmnImporter").default)[];
    })[];
}
export default _default;

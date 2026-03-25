export default class BpmnTreeWalker {
    /**
     * @param handler
     */
    constructor(handler: Record<'element' | 'root' | 'error', Function>);
    registerDi: (di: any) => void;
    /**
     * Handle definitions and return the rendered diagram (if any).
     *
     * @param definitions to walk and import
     * @param diagram specific diagram to import and display
     *
     * @throws {Error} if no diagram to display could be found
     */
    handleDefinitions: (definitions: ModdleElement, diagram?: ModdleElement) => void;
    handleDeferred: () => void;
    handleSubProcess: (subProcess: any, context: any) => void;
}

type ModdleElement = import('../model/Types').ModdleElement;

/**
 * A handler that updates the text of a BPMN element.
 *
 */
export default class UpdateLabelHandler {
    static $inject: string[];
    /**
     * @param modeling
     * @param textRenderer
     * @param bpmnFactory
     */
    constructor(modeling: Modeling, textRenderer: TextRenderer, bpmnFactory: BpmnFactory);
    preExecute: (ctx: any) => void;
    execute: (ctx: any) => any[];
    revert: (ctx: any) => any[];
    postExecute: (ctx: any) => void;
}

type Modeling = import('../../modeling/Modeling').default;
type TextRenderer = import('../../../draw/TextRenderer').default;
type BpmnFactory = import('../../modeling/BpmnFactory').default;
type Element = import('../../../model/Types').Element;

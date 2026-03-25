/**
 * BPMN-specific replace.
 *
 */
export default class BpmnReplace {
    static $inject: string[];
    /**
     * @param bpmnFactory
     * @param elementFactory
     * @param moddleCopy
     * @param modeling
     * @param replace
     * @param rules
     */
    constructor(bpmnFactory: BpmnFactory, elementFactory: ElementFactory, moddleCopy: ModdleCopy, modeling: Modeling, replace: Replace, rules: Rules);
    replaceElement: (element: Element, targetElement: TargetElement, hints?: Hints) => Element;
}

type BpmnFactory = import('../modeling/BpmnFactory').default;
type ElementFactory = import('../modeling/ElementFactory').default;
type ModdleCopy = import('../copy-paste/ModdleCopy').default;
type Modeling = import('../modeling/Modeling').default;
type Replace = import('diagram-js/lib/features/replace/Replace').default;
type Rules = import('diagram-js/lib/features/rules/Rules').default;
type Element = import('../../model/Types').Element;
type Shape = import('../../model/Types').Shape;
type ModdleElement = import('../../model/Types').ModdleElement;

export type TargetElement = {
    type: string;
    cancelActivity: boolean;
    instantiate: boolean;
    eventGatewayType: string;
    triggeredByEvent: boolean;
    isInterrupting: boolean;
    collapsed: boolean;
    isExpanded: boolean;
    eventDefinitionType: string;
    eventDefinitionAttrs: any;
    host: Shape;
};

export type Hints = {
    moveChildren: boolean;
} & Record<string, any>;

import { isExpanded } from '../../util/DiUtil';

/**
 * BPMN-specific replace behavior.
 *
 */
export default class ReplaceElementBehaviour extends CommandInterceptor {
  /**
   * @param bpmnReplace
   * @param bpmnRules
   * @param elementRegistry
   * @param injector
   * @param modeling
   * @param selection
   */
  constructor(bpmnReplace: BpmnReplace, bpmnRules: BpmnRules, elementRegistry: ElementRegistry, injector: Injector, modeling: Modeling, selection: Selection);
}

type BpmnReplace = import('../../replace/BpmnReplace').default;
type BpmnRules = import('../../rules/BpmnRules').default;
type ElementRegistry = import('diagram-js/lib/core/ElementRegistry').default;
type Injector = import('didi').Injector;
type Modeling = import('../Modeling').default;
type Selection = import('diagram-js/lib/features/selection/Selection').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

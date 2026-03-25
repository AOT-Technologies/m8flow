/**
 * Replace boundary event with intermediate event when creating or moving results in detached event.
 *
 */
export default class DetachEventBehavior extends CommandInterceptor {
  /**
   * @param bpmnReplace
   * @param injector
   */
  constructor(bpmnReplace: BpmnReplace, injector: Injector);
}

type BpmnReplace = import('../../replace/BpmnReplace').default;
type Injector = import('didi').Injector;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

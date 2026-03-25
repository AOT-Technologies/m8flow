/**
 * Replace intermediate event with boundary event when creating or moving results in attached event.
 *
 */
export default class AttachEventBehavior extends CommandInterceptor {
  /**
   * @param bpmnReplace
   * @param injector
   */
  constructor(bpmnReplace: BpmnReplace, injector: Injector);
}

type BpmnReplace = import('../../replace/BpmnReplace').default;
type Injector = import('didi').Injector;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

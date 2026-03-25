/**
 * Registers and executes BPMN specific editor actions.
 *
 */
export default class BpmnEditorActions extends EditorActions {
  /**
   * @param injector
   */
  constructor(injector: Injector);
}

type Injector = import('didi').Injector;
import EditorActions from 'diagram-js/lib/features/editor-actions/EditorActions';

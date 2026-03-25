/**
 * BPMN 2.0 specific keyboard bindings.
 *
 */
export default class BpmnKeyboardBindings extends KeyboardBindings {
    /**
     * @param injector
     */
    constructor(injector: Injector);
}

type Injector = import('didi').Injector;
type EditorActions = import('diagram-js/lib/features/editor-actions/EditorActions').default;
type Keyboard = import('diagram-js/lib/features/keyboard/Keyboard').default;
import KeyboardBindings from 'diagram-js/lib/features/keyboard/KeyboardBindings';

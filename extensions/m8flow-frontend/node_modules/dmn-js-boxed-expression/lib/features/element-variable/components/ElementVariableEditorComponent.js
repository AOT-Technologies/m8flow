import { createVNode, createComponentVNode, createTextVNode } from "inferno";
import InputSelect from 'dmn-js-shared/lib/components/InputSelect';
import { withChangeSupport } from '../../../util/withChangeSupport';
const VARIABLE_TYPE_ID = 'dmn-boxed-expression-variable-type';
export default class ElementVariableComponentProvider {
  static $inject = ['components', 'elementVariable'];
  constructor(components, elementVariable) {
    const component = withChangeSupport(ElementVariableComponent, () => [elementVariable.getVariable()]);
    components.onGetComponent('footer', () => component);
  }
}
function ElementVariableComponent(_, context) {
  const elementVariable = context.injector.get('elementVariable');
  const translate = context.injector.get('translate');
  const name = elementVariable.getName();
  return createVNode(1, "div", "element-variable", [createVNode(1, "h2", null, createTextVNode("Result"), 2), createVNode(1, "div", "element-variable-name", [createVNode(1, "span", "element-variable-name-label", translate('Variable name'), 0), createVNode(1, "span", null, name, 0)], 4), createVNode(1, "div", "element-variable-type", [createVNode(1, "label", "element-variable-type-label", createTextVNode("Result type"), 2, {
    "for": VARIABLE_TYPE_ID
  }), createComponentVNode(2, VariableTypeEditor)], 4)], 4);
}
function VariableTypeEditor(_, context) {
  const elementVariable = context.injector.get('elementVariable');
  const dataTypes = context.injector.get('dataTypes');
  const translate = context.injector.get('translate');
  const type = elementVariable.getType();
  const onChange = type => elementVariable.setType(type);
  const typeRefOptions = dataTypes.getAll().map(t => {
    return {
      label: translate(t),
      value: t
    };
  });
  return createComponentVNode(2, InputSelect, {
    "value": type,
    "onChange": onChange,
    "options": typeRefOptions,
    "id": VARIABLE_TYPE_ID
  });
}
//# sourceMappingURL=ElementVariableEditorComponent.js.map
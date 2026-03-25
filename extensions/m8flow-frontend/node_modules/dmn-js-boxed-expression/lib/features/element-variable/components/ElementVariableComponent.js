import { createVNode, createTextVNode } from "inferno";
export default class ElementVariableComponentProvider {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('footer', () => ElementVariableComponent);
  }
}
function ElementVariableComponent(_, context) {
  const elementVariable = context.injector.get('elementVariable');
  const translate = context.injector.get('translate');

  // there is only one single element
  const name = elementVariable.getName();
  const type = elementVariable.getType();
  return createVNode(1, "div", "element-variable", [createVNode(1, "h2", null, createTextVNode("Result"), 2), createVNode(1, "div", "element-variable-name", [createVNode(1, "span", "element-variable-name-label", translate('Variable name'), 0), createVNode(1, "span", null, name, 0)], 4), createVNode(1, "div", "element-variable-type", [createVNode(1, "span", "element-variable-type-label", translate('Variable type'), 0), createVNode(1, "span", null, type, 0)], 4)], 4);
}
//# sourceMappingURL=ElementVariableComponent.js.map
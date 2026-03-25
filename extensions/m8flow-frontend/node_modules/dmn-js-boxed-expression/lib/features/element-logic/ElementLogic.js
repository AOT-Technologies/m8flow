import { createVNode, createComponentVNode, createTextVNode } from "inferno";
import { is } from 'dmn-js-shared/lib/util/ModelUtil';
const FALLBACK_PRIORITY = 100;
export default class ElementLogic {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('body', () => {
      return LogicComponent;
    });
    components.onGetComponent('expression', FALLBACK_PRIORITY, () => FallbackExpression);
  }
}
function LogicComponent(_, {
  injector
}) {
  const components = injector.get('components');
  const viewer = injector.get('viewer');
  const rootElement = viewer.getRootElement();
  const expression = getLogic(rootElement);
  const Expression = components.getComponent('expression', {
    expression
  });
  return createComponentVNode(2, Expression, {
    "expression": expression
  });
}
function getLogic(element) {
  if (is(element, 'dmn:Decision')) {
    return element.get('decisionLogic');
  } else if (is(element, 'dmn:BusinessKnowledgeModel')) {
    return element.get('encapsulatedLogic');
  }
}
function FallbackExpression({
  expression
}) {
  return createVNode(1, "div", null, createVNode(1, "span", null, [createTextVNode("Expression of type "), expression.$type, createTextVNode(" is not supported.")], 0, {
    "style": "color:red;"
  }), 2);
}
//# sourceMappingURL=ElementLogic.js.map
import { createVNode } from "inferno";
import { is } from 'dmn-js-shared/lib/util/ModelUtil';
export class LiteralExpressionComponentProvider {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('expression', ({
      expression
    }) => {
      if (is(expression, 'dmn:LiteralExpression')) {
        return LiteralExpressionComponent;
      }
    });
  }
}
function LiteralExpressionComponent({
  expression
}, context) {
  const literalExpression = context.injector.get('literalExpression');
  const text = literalExpression.getText(expression);
  return createVNode(1, "div", "textarea", createVNode(1, "div", "content", text, 0), 2);
}
//# sourceMappingURL=LiteralExpressionComponent.js.map
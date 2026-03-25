import { createVNode } from "inferno";
import { Component } from 'inferno';
export default class LiteralExpressionPropertiesComponent extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    this._viewer = context.injector.get('viewer');
  }
  render() {
    const {
      decisionLogic: literalExpression,
      variable
    } = this._viewer.getDecision();
    return createVNode(1, "div", "literal-expression-properties", createVNode(1, "table", null, [createVNode(1, "tr", null, [createVNode(1, "td", null, this._translate('Variable name:'), 0), createVNode(1, "td", null, createVNode(1, "span", null, variable.name || '-', 0), 2)], 4), createVNode(1, "tr", null, [createVNode(1, "td", null, this._translate('Variable type:'), 0), createVNode(1, "td", null, createVNode(1, "span", null, this._translate(variable.typeRef || '') || '-', 0), 2)], 4), createVNode(1, "tr", null, [createVNode(1, "td", null, this._translate('Expression language:'), 0), createVNode(1, "td", null, createVNode(1, "span", null, literalExpression.expressionLanguage || '-', 0), 2)], 4)], 4), 2);
  }
}
//# sourceMappingURL=LiteralExpressionPropertiesComponent.js.map
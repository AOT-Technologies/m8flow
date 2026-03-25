import { createVNode, createComponentVNode, createTextVNode } from "inferno";
import { is } from 'dmn-js-shared/lib/util/ModelUtil';
export class FunctionDefinitionComponentProvider {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('expression', ({
      expression
    }) => {
      if (is(expression, 'dmn:FunctionDefinition')) {
        return FunctionDefinitionComponent;
      }
    });
  }
}
function FunctionDefinitionComponent({
  expression
}, context) {
  const functionDefinition = context.injector.get('functionDefinition');
  const kind = functionDefinition.getKind(expression);
  const parameters = functionDefinition.getParameters(expression);
  const body = functionDefinition.getBody(expression);
  return createVNode(1, "div", "function-definition", [createComponentVNode(2, Kind, {
    "kind": kind
  }), createComponentVNode(2, FormalParameters, {
    "parameters": parameters
  }), createComponentVNode(2, BodyExpression, {
    "expression": body
  })], 4);
}
const KIND_MAP = {
  'FEEL': 'F',
  'Java': 'J',
  'PMML': 'P'
};
function Kind({
  kind
}, context) {
  const translate = context.injector.get('translate');
  return createVNode(1, "div", "function-definition-kind", KIND_MAP[kind], 0, {
    "title": translate('Function kind: {kind}', {
      kind
    })
  });
}
function FormalParameters({
  parameters
}) {
  return createVNode(1, "div", "function-definition-parameters", createVNode(1, "div", null, [createTextVNode("("), parameters.reduce((acc, parameter) => {
    return acc.concat(createComponentVNode(2, Parameter, {
      "parameter": parameter
    }), ', ');
  }, []).slice(0, -1), createTextVNode(")")], 0), 2);
}
function Parameter({
  parameter
}) {
  const {
    name,
    typeRef
  } = parameter;
  const displayedName = name || '<unnamed>';
  return createVNode(1, "span", null, typeRef ? `${displayedName}: ${typeRef}` : displayedName, 0);
}
function BodyExpression({
  expression
}, context) {
  const Expression = context.components.getComponent('expression', {
    expression
  });
  return createVNode(1, "div", "function-definition-body", createComponentVNode(2, Expression, {
    "expression": expression
  }), 2);
}
//# sourceMappingURL=FunctionDefinitionComponent.js.map
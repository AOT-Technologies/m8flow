import { createVNode, createComponentVNode, createTextVNode } from "inferno";
import InputSelect from 'dmn-js-shared/lib/components/InputSelect';
import Input from 'dmn-js-shared/lib/components/Input';
import { withChangeSupport } from '../../../util/withChangeSupport';
export class FormalParametersEditorProvider {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('context-menu', (context = {}) => {
      if (context.contextMenuType && context.contextMenuType === 'formal-parameters-editor') {
        return FormalParametersEditor;
      }
    });
  }
}
const FormalParametersEditor = withChangeSupport(_FormalParametersEditor, props => [props.context.expression]);
function _FormalParametersEditor({
  context: {
    expression
  }
}, context) {
  const functionDefinition = context.injector.get('functionDefinition');
  const translate = context.injector.get('translate');
  const parameters = functionDefinition.getParameters(expression);
  const remove = parameter => {
    functionDefinition.removeParameter(expression, parameter);
  };
  const add = () => {
    functionDefinition.addParameter(expression);
  };
  return createVNode(1, "div", "context-menu-container formal-parameters", [createVNode(1, "h3", null, translate('Edit formal parameters'), 0), parameters.length ? createVNode(1, "table", null, [createVNode(1, "thead", null, createVNode(1, "tr", null, [createVNode(1, "th", null, createTextVNode("Name"), 2), createVNode(1, "th", null, createTextVNode("Type"), 2)], 4), 2), createVNode(1, "tbody", null, parameters.map((parameter, idx) => createComponentVNode(2, Parameter, {
    "parameter": parameter,
    "remove": () => remove(parameter)
  }, idx)), 0)], 4) : null, createVNode(1, "button", "add-parameter", translate('Add parameter'), 0, {
    "type": "button",
    "onClick": add
  })], 0);
}
const Parameter = withChangeSupport(function ({
  parameter,
  remove
}, context) {
  const dataTypes = context.injector.get('dataTypes');
  const translate = context.injector.get('translate');
  const functionDefinition = context.injector.get('functionDefinition');
  const {
    name,
    typeRef
  } = parameter;
  const onNameChange = name => {
    functionDefinition.updateParameter(parameter, {
      name
    });
  };
  const onTypeRefChange = typeRef => {
    functionDefinition.updateParameter(parameter, {
      typeRef
    });
  };
  const typeRefOptions = dataTypes.getAll().map(t => {
    return {
      label: translate(t),
      value: t
    };
  });
  return createVNode(1, "tr", "function-definition-parameter", [createVNode(1, "td", null, createComponentVNode(2, Input, {
    "onChange": onNameChange,
    "value": name
  }), 2), createVNode(1, "td", null, createComponentVNode(2, InputSelect, {
    "onChange": onTypeRefChange,
    "value": typeRef,
    "options": typeRefOptions
  }), 2), createVNode(1, "td", null, createVNode(1, "button", "dmn-icon-trash", null, 1, {
    "type": "button",
    "onClick": remove,
    "aria-label": translate('Remove parameter')
  }), 2)], 4);
}, props => [props.parameter]);
//# sourceMappingURL=FormalParametersEditor.js.map
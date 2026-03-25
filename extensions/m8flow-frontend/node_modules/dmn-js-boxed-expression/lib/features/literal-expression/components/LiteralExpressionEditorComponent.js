import { createVNode, createComponentVNode, normalizeProps } from "inferno";
import { Component } from 'inferno';
import { is, isFeel } from 'dmn-js-shared/lib/util/ModelUtil';
import EditableComponent from 'dmn-js-shared/lib/components/EditableComponent';
import LiteralExpression from 'dmn-js-shared/lib/components/LiteralExpression';
import { withChangeSupport } from '../../../util/withChangeSupport';
class _LiteralExpressionEditorComponent extends Component {
  constructor(props, context) {
    super(props, context);
    this._literalExpression = context.injector.get('literalExpression');
    this._translate = context.injector.get('translate');
    this._expressionLanguages = context.injector.get('expressionLanguages');
    this._variableResolver = context.injector.get('variableResolver', false);
  }
  getLiteralExpression() {
    return this.props.expression;
  }
  editLiteralExpressionText = text => {
    const literalExpression = this.getLiteralExpression();
    this._literalExpression.setText(literalExpression, text);
  };
  getEditor() {
    return this.isFeel() ? FeelEditor : TextEditor;
  }
  isFeel() {
    const businessObject = this.getLiteralExpression();
    return isFeel(businessObject);
  }
  _getVariables() {
    const businessObject = this.getLiteralExpression();
    return this._variableResolver && this._variableResolver.getVariables(businessObject);
  }
  render() {
    // there is only one single element
    const {
      text
    } = this.getLiteralExpression();
    const Editor = this.getEditor();
    const variables = this._getVariables();
    const label = this._translate('Literal expression');
    return createComponentVNode(2, Editor, {
      "label": label,
      "className": "textarea editor",
      "value": text,
      "onChange": this.editLiteralExpressionText,
      "variables": variables
    });
  }
}
function FeelEditor(props) {
  return normalizeProps(createComponentVNode(2, LiteralExpression, {
    ...props,
    "onChange": props.onChange
  }));
}
class TextEditor extends EditableComponent {
  render() {
    return createVNode(1, "div", this.getClassName(), this.getEditor(), 0);
  }
}
const LiteralExpressionEditorComponent = withChangeSupport(_LiteralExpressionEditorComponent, props => [props.expression]);
export class LiteralExpressionEditorComponentProvider {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('expression', ({
      expression
    }) => {
      if (is(expression, 'dmn:LiteralExpression')) {
        return LiteralExpressionEditorComponent;
      }
    });
  }
}
//# sourceMappingURL=LiteralExpressionEditorComponent.js.map
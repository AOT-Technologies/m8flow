import { createVNode, createComponentVNode } from "inferno";
import InputSelect from 'dmn-js-shared/lib/components/InputSelect';
import { getBusinessObject, isInput } from 'dmn-js-shared/lib/util/ModelUtil';
export default class ExpressionLanguage {
  constructor(components, elementRegistry, modeling, expressionLanguages, translate, contextMenu) {
    this._modeling = modeling;
    this._translate = translate;
    this._expressionLanguages = expressionLanguages;
    components.onGetComponent('context-menu-cell-additional', (context = {}) => {
      if (context.contextMenuType && context.contextMenuType === 'context-menu') {
        const {
          event,
          id
        } = context;
        if (!id) {
          return;
        }
        const element = elementRegistry.get(id);

        // element might not be in element registry (e.g. cut)
        if (!element) {
          return;
        }
        if (!this._shouldDisplayContextMenuEntry(element)) {
          return;
        }
        const openMenu = clickEvent => {
          contextMenu.open({
            x: (event || clickEvent).pageX,
            y: (event || clickEvent).pageY
          }, {
            contextMenuType: 'expression-language',
            id
          });
        };
        return createVNode(1, "div", "context-menu-group-entry", this._translate('Change cell expression language'), 0, {
          "onClick": openMenu
        });
      }
    });
    components.onGetComponent('context-menu', (context = {}) => {
      if (context.contextMenuType && context.contextMenuType === 'expression-language') {
        const {
          id
        } = context;
        if (!id) {
          return;
        }
        const element = elementRegistry.get(id);

        // element might not be in element registry (e.g. cut)
        if (!element) {
          return;
        }
        const expressionLanguage = this._getElementExpressionLanguage(element);
        const options = expressionLanguages.getAll();
        const className = 'context-menu-group-entry ' + 'context-menu-entry-set-expression-language';
        const label = this._translate('Expression language');
        return () => createVNode(1, "div", "context-menu-flex", createVNode(1, "div", "context-menu-group", createVNode(1, "div", className, [createVNode(1, "div", null, label, 0), createComponentVNode(2, InputSelect, {
          "label": label,
          "className": "expression-language",
          "onChange": value => this.onChange(element, value),
          "options": options,
          "value": expressionLanguage
        })], 4), 2), 2);
      }
    });
    components.onGetComponent('context-menu', (context = {}) => {
      if (context.contextMenuType === 'input-edit') {
        return () => {
          const {
            inputExpression
          } = context.input;
          if (!this._shouldDisplayContextMenuEntry(inputExpression)) {
            return;
          }
          const expressionLanguage = this._getElementExpressionLanguage(inputExpression);
          const options = expressionLanguages.getAll();
          const label = this._translate('Expression language');
          return createVNode(1, "div", "context-menu-container ref-language", createVNode(1, "div", "dms-form-control", [createVNode(1, "label", "dms-label", label, 0), createComponentVNode(2, InputSelect, {
            "label": label,
            "className": "ref-language",
            "value": expressionLanguage || '',
            "onChange": value => this.onChange(inputExpression, value),
            "options": options
          })], 4), 2);
        };
      }
    });
  }
  onChange(element, expressionLanguage) {
    this._modeling.editExpressionLanguage(element, expressionLanguage);
  }
  _shouldDisplayContextMenuEntry(element) {
    const expressionLanguages = this._expressionLanguages.getAll();
    if (expressionLanguages.length > 1) {
      return true;
    }
    const expressionLanguage = this._getElementExpressionLanguage(element);
    return expressionLanguage !== this._getDefaultElementExpressionLanguage(element);
  }
  _getElementExpressionLanguage(element) {
    return getBusinessObject(element).expressionLanguage || this._getDefaultElementExpressionLanguage(element);
  }
  _getDefaultElementExpressionLanguage(element) {
    return this._expressionLanguages.getDefault(isInput(element.col) ? 'inputCell' : 'outputCell').value;
  }
}
ExpressionLanguage.$inject = ['components', 'elementRegistry', 'modeling', 'expressionLanguages', 'translate', 'contextMenu'];
//# sourceMappingURL=ExpressionLanguage.js.map
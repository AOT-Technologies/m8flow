import { createVNode, createComponentVNode } from "inferno";
import InputSelect from 'dmn-js-shared/lib/components/InputSelect';
const KIND_OPTIONS = [{
  value: 'FEEL',
  label: 'FEEL'
}, {
  value: 'Java',
  label: 'Java'
}, {
  value: 'PMML',
  label: 'PMML'
}];
export class KindEditorProvider {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('context-menu', (context = {}) => {
      if (context.contextMenuType && context.contextMenuType === 'kind-editor') {
        return KindEditor;
      }
    });
  }
}
function KindEditor({
  context: {
    expression
  }
}, context) {
  const functionDefinition = context.injector.get('functionDefinition');
  const translate = context.injector.get('translate');
  const kind = functionDefinition.getKind(expression);
  const setKind = value => {
    functionDefinition.setKind(expression, value);
  };
  return createVNode(1, "div", "context-menu-container", [createVNode(1, "h3", null, translate('Edit function kind'), 0), createComponentVNode(2, InputSelect, {
    "label": translate('Kind'),
    "options": KIND_OPTIONS,
    "value": kind,
    "onChange": setKind,
    "noInput": true
  })], 4);
}
//# sourceMappingURL=KindEditor.js.map
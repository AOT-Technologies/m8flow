import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
import { is } from 'dmn-js-shared/lib/util/ModelUtil';
import { inject } from 'table-js/lib/components';
export default class DecisionTablePropertiesComponent extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    inject(this);
  }
  render() {
    const root = this.sheet.getRoot();
    if (!is(root, 'dmn:DMNElement')) {
      return null;
    }
    const {
      name
    } = root.businessObject.$parent;
    const HitPolicy = this.components.getComponent('hit-policy') || NullComponent;
    return createVNode(1, "div", "decision-table-properties", [createVNode(1, "div", "decision-table-name", name, 0, {
      "title": this._translate('Decision name: ') + name
    }), createVNode(1, "div", "decision-table-header-separator"), createComponentVNode(2, HitPolicy)], 4);
  }
}
DecisionTablePropertiesComponent.$inject = ['sheet', 'components'];
function NullComponent() {
  return null;
}
//# sourceMappingURL=DecisionTablePropertiesComponent.js.map
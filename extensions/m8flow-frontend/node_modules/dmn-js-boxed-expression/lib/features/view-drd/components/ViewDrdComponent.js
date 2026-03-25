import { createVNode } from "inferno";
import { Component } from 'inferno';
export default class ViewDrdComponent extends Component {
  constructor(props, context) {
    super(props, context);
    const {
      injector
    } = context;
    this._translate = injector.get('translate');
    this._eventBus = injector.get('eventBus');
  }
  onClick = () => {
    this._eventBus.fire('showDrd');
  };
  render() {
    return createVNode(1, "div", "view-drd", createVNode(1, "button", "view-drd-button", this._translate('View DRD'), 0, {
      "type": "button",
      "onClick": this.onClick
    }), 2, null, null, node => this.node = node);
  }
}
ViewDrdComponent.$inject = ['translate'];
//# sourceMappingURL=ViewDrdComponent.js.map
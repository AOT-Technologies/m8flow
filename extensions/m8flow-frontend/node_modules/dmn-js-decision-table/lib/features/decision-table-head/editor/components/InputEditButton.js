import { createVNode } from "inferno";
import { Component } from 'inferno';
export class InputEditButton extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    this._eventBus = context.injector.get('eventBus');
  }
  onClick = event => {
    const {
      col: input
    } = this.props;
    this._eventBus.fire('input.edit', {
      event,
      input
    });
  };
  render() {
    return createVNode(1, "button", "edit-button dmn-icon-edit", null, 1, {
      "aria-label": this._translate('Edit input'),
      "type": "button",
      "onClick": this.onClick
    });
  }
}
//# sourceMappingURL=InputEditButton.js.map
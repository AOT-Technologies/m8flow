import { createVNode } from "inferno";
import { Component } from 'inferno';
export class OutputEditButton extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    this._eventBus = context.injector.get('eventBus');
  }
  onClick = event => {
    const {
      col: output
    } = this.props;
    this._eventBus.fire('output.edit', {
      event,
      output
    });
  };
  render() {
    return createVNode(1, "button", "edit-button dmn-icon-edit", null, 1, {
      "aria-label": this._translate('Edit output'),
      "type": "button",
      "onClick": this.onClick
    });
  }
}
//# sourceMappingURL=OutputEditButton.js.map
import { createVNode, createTextVNode } from "inferno";
import { Component } from 'inferno';
import { inject } from 'table-js/lib/components';
export default class CreateInputsCell extends Component {
  constructor(props, context) {
    super(props, context);
    inject(this);
  }
  onClick = event => {
    this.editorActions.trigger('addInput');
  };
  render() {
    return createVNode(1, "td", "input-cell create-inputs", createTextVNode("-"), 2, {
      "onClick": this.onClick,
      "title": this.translate('Add input')
    });
  }
}
CreateInputsCell.$inject = ['editorActions', 'translate'];
//# sourceMappingURL=CreateInputCell.js.map
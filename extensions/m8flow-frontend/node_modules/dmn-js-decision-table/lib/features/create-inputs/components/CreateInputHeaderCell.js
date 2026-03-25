import { createVNode, createTextVNode } from "inferno";
import { Component } from 'inferno';
import { inject } from 'table-js/lib/components';
export default class CreateInputsHeaderCell extends Component {
  constructor(props, context) {
    super(props, context);
    inject(this);
  }
  onClick = event => {
    this.editorActions.trigger('addInput');
  };
  render() {
    return createVNode(1, "th", "input-cell create-inputs header actionable", [this.translate('Input'), createTextVNode(" "), createVNode(1, "button", "add-input dmn-icon-plus action-icon", null, 1, {
      "title": this.translate('Add input')
    })], 0, {
      "onClick": this.onClick,
      "title": this.translate('Add input')
    });
  }
}
CreateInputsHeaderCell.$inject = ['editorActions', 'translate'];
//# sourceMappingURL=CreateInputHeaderCell.js.map
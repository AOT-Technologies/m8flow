import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
import ContentEditable from 'dmn-js-shared/lib/components/ContentEditable';
import Input from 'dmn-js-shared/lib/components/Input';
export default class OutputEditor extends Component {
  constructor(props, context) {
    super(props, context);
    this.translate = context.injector ? context.injector.get('translate') : noopTranslate;
    this.setName = name => {
      name = name || undefined;
      this.handleChange({
        name
      });
    };
    this.setLabel = label => {
      label = label || undefined;
      this.handleChange({
        label
      });
    };
  }
  handleChange(changes) {
    var {
      onChange
    } = this.props;
    if (typeof onChange === 'function') {
      onChange(changes);
    }
  }
  render() {
    const {
      name,
      label
    } = this.props;
    return createVNode(1, "div", "context-menu-container ref-output-editor output-edit", [createVNode(1, "div", "dms-form-control", createComponentVNode(2, ContentEditable, {
      "label": this.translate('Output label'),
      "className": "dms-output-label",
      "value": label || '',
      "placeholder": this.translate('Output'),
      "singleLine": true,
      "onInput": this.setLabel
    }), 2), createVNode(1, "div", "dms-form-control", [createVNode(1, "label", "dms-label", this.translate('Output name'), 0), createComponentVNode(2, Input, {
      "label": this.translate('Output name'),
      "className": "ref-output-name",
      "value": name || '',
      "onInput": this.setName
    })], 4)], 4);
  }
}
function noopTranslate(str) {
  return str;
}
//# sourceMappingURL=OutputEditor.js.map
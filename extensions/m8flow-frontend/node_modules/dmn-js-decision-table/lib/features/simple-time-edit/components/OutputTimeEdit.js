import { createVNode, createComponentVNode, createTextVNode } from "inferno";
import { Component } from 'inferno';
import ValidatedInput from 'dmn-js-shared/lib/components/ValidatedInput';
import { getSampleTime, validateISOString, parseString } from '../Utils';
import { getSampleDate } from '../../simple-date-edit/Utils';
export default class OutputTimeEdit extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    this._modeling = context.injector.get('modeling');
    const {
      element
    } = this.props.context;
    const parsedString = parseString(element.businessObject.text);
    this.state = {
      date: parsedString ? parsedString.date : ''
    };
    const debounceInput = context.injector.get('debounceInput');
    this.debouncedEditCell = debounceInput(this.editCell.bind(this));
    this.editCell = this.editCell.bind(this);
    this.onClick = this.onClick.bind(this);
    this.onInput = this.onInput.bind(this);
  }
  editCell(cell, text) {
    this._modeling.editCell(cell, text);
  }
  onClick() {
    const {
      element
    } = this.props.context;
    const date = getSampleTime();
    this.setState({
      date
    });
    this.editCell(element.businessObject, `time("${date}")`);
  }
  onInput({
    value
  }) {
    const {
      element
    } = this.props.context;
    this.setState({
      date: value
    });
    this.debouncedEditCell(element.businessObject, `time("${value}")`);
  }
  render() {
    const {
      date
    } = this.state;
    return createVNode(1, "div", "context-menu-container simple-time-edit", [createVNode(1, "h3", "dms-heading", this._translate('Edit time'), 0), createVNode(1, "h4", "dms-heading", this._translate('Set time'), 0), createVNode(1, "div", null, [createComponentVNode(2, ValidatedInput, {
      "label": this._translate('Time value'),
      "onInput": this.onInput,
      "placeholder": this._translate('e.g. { example } ', {
        example: getSampleDate()
      }),
      "validate": string => validateISOString(string) && this._translate(validateISOString(string)),
      "value": date,
      "className": "dms-block"
    }), createVNode(1, "p", "dms-hint", [createVNode(1, "button", "use-now", this._translate('Use now'), 0, {
      "type": "button",
      "onClick": this.onClick
    }), createTextVNode(".")], 4)], 4)], 4);
  }
}
//# sourceMappingURL=OutputTimeEdit.js.map
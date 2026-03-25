import { createVNode, createComponentVNode, createTextVNode } from "inferno";
import { Component } from 'inferno';
import ValidatedInput from 'dmn-js-shared/lib/components/ValidatedInput';
import InputSelect from 'dmn-js-shared/lib/components/InputSelect';
import { getTimeString, getSampleTime, validateISOString, parseString } from '../Utils';
import { getSampleDate } from '../../simple-date-edit/Utils';
const EXACT = 'exact',
  BEFORE = 'before',
  AFTER = 'after',
  BETWEEN = 'between';
export default class InputTimeEdit extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    this._modeling = context.injector.get('modeling');
    const {
      element
    } = this.props.context;
    const parsedString = parseString(element.businessObject.text);
    if (parsedString) {
      let times;
      if (parsedString.time) {
        times = [parsedString.time, ''];
      } else if (parsedString.times) {
        times = parsedString.times;
      } else {
        times = ['', ''];
      }
      this.state = {
        type: parsedString.type,
        times: times
      };
    } else {
      this.state = {
        type: EXACT,
        times: ['', '']
      };
    }
    const debounceInput = context.injector.get('debounceInput');
    this.debouncedEditCell = debounceInput(this.editCell.bind(this));
    this.editCell = this.editCell.bind(this);
    this.onTypeChange = this.onTypeChange.bind(this);
    this.onSetStartTimeNowClick = this.onSetStartTimeNowClick.bind(this);
    this.onSetEndTimeNowClick = this.onSetEndTimeNowClick.bind(this);
    this.onStartTimeInput = this.onStartTimeInput.bind(this);
    this.onEndTimeInput = this.onEndTimeInput.bind(this);
  }
  editCell(cell, text) {
    this._modeling.editCell(cell, text);
  }
  onTypeChange(value) {
    const {
      element
    } = this.props.context;
    const {
      times
    } = this.state;
    this.setState({
      type: value
    });
    if (parseString(getTimeString(value, times))) {
      this.editCell(element.businessObject, getTimeString(value, times));
    }
  }
  onSetStartTimeNowClick() {
    const {
      element
    } = this.props.context;
    const {
      times,
      type
    } = this.state;
    const time = getSampleTime();
    this.setState({
      times: [time, times[1]]
    });
    if (parseString(getTimeString(type, [time, times[1]]))) {
      this.editCell(element.businessObject, getTimeString(type, [time, times[1]]));
    }
  }
  onSetEndTimeNowClick() {
    const {
      element
    } = this.props.context;
    const {
      times,
      type
    } = this.state;
    const time = getSampleTime();
    this.setState({
      times: [times[0], time]
    });
    if (parseString(getTimeString(type, [times[0], time]))) {
      this.editCell(element.businessObject, getTimeString(type, [times[0], time]));
    }
  }
  onStartTimeInput({
    value
  }) {
    const {
      element
    } = this.props.context;
    const {
      times,
      type
    } = this.state;
    this.setState({
      times: [value, times[1]]
    });
    this.debouncedEditCell(element.businessObject, getTimeString(type, [value, times[1]]));
  }
  onEndTimeInput({
    value
  }) {
    const {
      element
    } = this.props.context;
    const {
      times,
      type
    } = this.state;
    this.setState({
      times: [times[0], value]
    });
    this.debouncedEditCell(element.businessObject, getTimeString(type, [times[0], value]));
  }
  render() {
    const {
      times,
      type
    } = this.state;
    const options = [{
      label: this._translate('Exactly'),
      value: EXACT
    }, {
      label: this._translate('Before'),
      value: BEFORE
    }, {
      label: this._translate('After'),
      value: AFTER
    }, {
      label: this._translate('Between'),
      value: BETWEEN
    }];
    return createVNode(1, "div", "context-menu-container simple-time-edit", [createVNode(1, "h3", "dms-heading", this._translate('Edit time'), 0), createVNode(1, "div", "dms-fill-row", createComponentVNode(2, InputSelect, {
      "label": this._translate('Time'),
      "noInput": true,
      "onChange": this.onTypeChange,
      "options": options,
      "value": type
    }), 2), createVNode(1, "h4", "dms-heading", type === BETWEEN ? this._translate('Edit start time') : this._translate('Set time'), 0), createVNode(1, "div", null, [createComponentVNode(2, ValidatedInput, {
      "label": this._translate('Start time'),
      "className": "start-time-input dms-block",
      "onInput": this.onStartTimeInput,
      "placeholder": this._translate('e.g. { example } ', {
        example: getSampleDate()
      }),
      "validate": string => validateISOString(string) && this._translate(validateISOString(string)),
      "value": times[0]
    }), createVNode(1, "p", "dms-hint", [createVNode(1, "button", "use-now", this._translate('Use now'), 0, {
      "type": "button",
      "onClick": this.onSetStartTimeNowClick
    }), createTextVNode(".")], 4)], 4), type === BETWEEN && createVNode(1, "h4", "dms-heading", this._translate('Edit end time'), 0), type === BETWEEN && createVNode(1, "div", null, [createComponentVNode(2, ValidatedInput, {
      "label": this._translate('End time'),
      "className": "end-time-input dms-block",
      "onInput": this.onEndTimeInput,
      "placeholder": this._translate('e.g. { example } ', {
        example: getSampleDate()
      }),
      "validate": string => validateISOString(string) && this._translate(validateISOString(string)),
      "value": times[1]
    }), createVNode(1, "p", "dms-hint", [createVNode(1, "button", "use-now", this._translate('Use now'), 0, {
      "type": "button",
      "onClick": this.onSetEndTimeNowClick
    }), createTextVNode(".")], 4)], 4)], 0);
  }
}
//# sourceMappingURL=InputTimeEdit.js.map
import { createVNode, createComponentVNode, createTextVNode } from "inferno";
import { Component } from 'inferno';
import Input from 'dmn-js-shared/lib/components/Input';
import InputSelect from 'dmn-js-shared/lib/components/InputSelect';
import { getComparisonString, getRangeString, parseString } from '../Utils';
const COMPARISON = 'comparison',
  RANGE = 'range';
export default class InputNumberEdit extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    this._modeling = context.injector.get('modeling');
    const {
      element
    } = this.props.context;
    const parsedString = parseString(element.businessObject.text);
    if (parsedString) {
      this.state = {
        type: parsedString.type,
        comparisonOperator: parsedString.operator || 'equals',
        comparisonValue: parsedString.value || 0,
        rangeStartValue: parsedString.values ? parsedString.values[0] : 0,
        rangeEndValue: parsedString.values ? parsedString.values[1] : 0,
        rangeStartType: parsedString.start || 'include',
        rangeEndType: parsedString.end || 'include'
      };
    } else {
      this.state = {
        type: COMPARISON,
        comparisonOperator: 'equals',
        comparisonValue: 0,
        rangeStartValue: 0,
        rangeEndValue: 0,
        rangeStartType: 'include',
        rangeEndType: 'include'
      };
    }
    const debounceInput = context.injector.get('debounceInput');
    this.debouncedEditCell = debounceInput(this.editCell.bind(this));
    this.editCell = this.editCell.bind(this);
    this.onComparisonOperatorChange = this.onComparisonOperatorChange.bind(this);
    this.onComparisonValueChange = this.onComparisonValueChange.bind(this);
    this.onTypeChange = this.onTypeChange.bind(this);
    this.onRangeStartTypeChange = this.onRangeStartTypeChange.bind(this);
    this.onRangeStartValueChange = this.onRangeStartValueChange.bind(this);
    this.onRangeEndTypeChange = this.onRangeEndTypeChange.bind(this);
    this.onRangeEndValueChange = this.onRangeEndValueChange.bind(this);
  }
  editCell(cell, text) {
    this._modeling.editCell(cell, text);
  }
  onTypeChange(value) {
    const {
      element
    } = this.props.context;
    const {
      comparisonOperator,
      comparisonValue,
      rangeStartValue,
      rangeEndValue,
      rangeStartType,
      rangeEndType
    } = this.state;
    if (value === COMPARISON) {
      this.editCell(element.businessObject, getComparisonString(comparisonOperator, comparisonValue));
    } else {
      this.editCell(element.businessObject, getRangeString(rangeStartValue, rangeEndValue, rangeStartType, rangeEndType));
    }
    this.setState({
      type: value
    });
  }
  onComparisonOperatorChange(value) {
    const {
      element
    } = this.props.context;
    const {
      type,
      comparisonValue
    } = this.state;
    if (type === COMPARISON) {
      this.editCell(element.businessObject, getComparisonString(value, comparisonValue));
      this.setState({
        comparisonOperator: value
      });
    }
  }
  onComparisonValueChange(comparisonValue) {
    const {
      element
    } = this.props.context;
    const {
      type,
      comparisonOperator
    } = this.state;
    if (type === COMPARISON) {
      this.debouncedEditCell(element.businessObject, getComparisonString(comparisonOperator, comparisonValue));
      this.setState({
        comparisonValue
      });
    }
  }
  onRangeStartTypeChange(value) {
    const {
      element
    } = this.props.context;
    const {
      type,
      rangeStartValue,
      rangeEndValue,
      rangeEndType
    } = this.state;
    if (type === RANGE) {
      this.editCell(element.businessObject, getRangeString(rangeStartValue, rangeEndValue, value, rangeEndType));
      this.setState({
        rangeStartType: value
      });
    }
  }
  onRangeStartValueChange(value) {
    const {
      element
    } = this.props.context;
    const {
      type,
      rangeEndValue,
      rangeStartType,
      rangeEndType
    } = this.state;
    if (type === RANGE) {
      this.editCell(element.businessObject, getRangeString(value, rangeEndValue, rangeStartType, rangeEndType));
      this.setState({
        rangeStartValue: value
      });
    }
  }
  onRangeEndTypeChange(value) {
    const {
      element
    } = this.props.context;
    const {
      type,
      rangeStartValue,
      rangeEndValue,
      rangeStartType
    } = this.state;
    if (type === RANGE) {
      this.editCell(element.businessObject, getRangeString(rangeStartValue, rangeEndValue, rangeStartType, value));
      this.setState({
        rangeEndType: value
      });
    }
  }
  onRangeEndValueChange(value) {
    const {
      element
    } = this.props.context;
    const {
      type,
      rangeStartValue,
      rangeStartType,
      rangeEndType
    } = this.state;
    if (type === RANGE) {
      this.editCell(element.businessObject, getRangeString(rangeStartValue, value, rangeStartType, rangeEndType));
      this.setState({
        rangeEndValue: value
      });
    }
  }
  renderComparison(comparisonOperator, comparisonValue) {
    const comparisonOperatorOptions = [{
      label: this._translate('Equals'),
      value: 'equals'
    }, {
      label: this._translate('Less'),
      value: 'less'
    }, {
      label: this._translate('Less or equals'),
      value: 'lessEquals'
    }, {
      label: this._translate('Greater'),
      value: 'greater'
    }, {
      label: this._translate('Greater or equals'),
      value: 'greaterEquals'
    }];
    return createVNode(1, "div", "comparison", [createVNode(1, "h4", "dms-heading", this._translate('Value'), 0), createVNode(1, "div", "dms-fill-row", [createComponentVNode(2, InputSelect, {
      "label": this._translate('Comparison operator'),
      "noInput": true,
      "onChange": this.onComparisonOperatorChange,
      "options": comparisonOperatorOptions,
      "value": comparisonOperator
    }), createTextVNode("\xA0"), createComponentVNode(2, Input, {
      "label": this._translate('Value'),
      "className": "comparison-number-input",
      "onInput": this.onComparisonValueChange,
      "type": "number",
      "value": comparisonValue
    })], 4)], 4);
  }
  renderRange(rangeStartValue, rangeEndValue, rangeStartType, rangeEndType) {
    const rangeTypeOptions = [{
      label: this._translate('Include'),
      value: 'include'
    }, {
      label: this._translate('Exclude'),
      value: 'exclude'
    }];
    return createVNode(1, "div", "range", [createVNode(1, "h4", "dms-heading", this._translate('Start value'), 0), createVNode(1, "div", "dms-fill-row", [createComponentVNode(2, InputSelect, {
      "label": this._translate('Start value'),
      "noInput": true,
      "onChange": this.onRangeStartTypeChange,
      "options": rangeTypeOptions,
      "value": rangeStartType
    }), createTextVNode("\xA0"), createComponentVNode(2, Input, {
      "className": "range-start-number-input",
      "onInput": this.onRangeStartValueChange,
      "type": "number",
      "value": rangeStartValue
    })], 4), createVNode(1, "h4", "dms-heading", this._translate('End value'), 0), createVNode(1, "div", "dms-fill-row", [createComponentVNode(2, InputSelect, {
      "label": this._translate('End value'),
      "noInput": true,
      "onChange": this.onRangeEndTypeChange,
      "options": rangeTypeOptions,
      "value": rangeEndType
    }), createTextVNode("\xA0"), createComponentVNode(2, Input, {
      "className": "range-end-number-input",
      "onInput": this.onRangeEndValueChange,
      "type": "number",
      "value": rangeEndValue
    })], 4)], 4);
  }
  render() {
    const {
      type,
      comparisonOperator,
      comparisonValue,
      rangeStartValue,
      rangeEndValue,
      rangeStartType,
      rangeEndType
    } = this.state;
    const typeOptions = [{
      label: this._translate('Comparison'),
      value: COMPARISON
    }, {
      label: this._translate('Range'),
      value: RANGE
    }];
    return createVNode(1, "div", "context-menu-container simple-number-edit", [createVNode(1, "h3", "dms-heading", this._translate('Edit number'), 0), createVNode(1, "div", "dms-fill-row", createComponentVNode(2, InputSelect, {
      "label": this._translate('Test type'),
      "noInput": true,
      "onChange": this.onTypeChange,
      "options": typeOptions,
      "value": type
    }), 2), type === COMPARISON && this.renderComparison(comparisonOperator, comparisonValue), type === RANGE && this.renderRange(rangeStartValue, rangeEndValue, rangeStartType, rangeEndType)], 0);
  }
}
//# sourceMappingURL=InputNumberEdit.js.map
import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
import { is } from 'dmn-js-shared/lib/util/ModelUtil';
import List from 'dmn-js-shared/lib/components/List';
import ValidatedInput from 'dmn-js-shared/lib/components/ValidatedInput';
import { getValuesArray, parseString } from '../Utils';
export default class AllowedValuesEditing extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    this._modeling = context.injector.get('modeling');
    this._changeSupport = context.changeSupport;
    const target = this.getAllowedValuesTarget();
    const parsedString = parseString(target.inputValues && target.inputValues.text || target.outputValues && target.outputValues.text || '');
    if (parsedString) {
      this.state = {
        values: parsedString.values.map(value => {
          return {
            value,
            isCheckable: false,
            isRemovable: true,
            group: this._translate('Predefined values')
          };
        }),
        inputValue: ''
      };
    } else {
      this.state = {
        values: null,
        inputValue: ''
      };
    }
  }
  onElementsChanged = () => {
    this.forceUpdate();
  };
  componentWillMount() {
    const target = this.getAllowedValuesTarget();
    this._changeSupport.onElementsChanged(target.id, this.onElementsChanged);
  }
  componentWillUnmount() {
    const target = this.getAllowedValuesTarget();
    this._changeSupport.offElementsChanged(target.id, this.onElementsChanged);
  }
  setPredefinedValues = values => {
    // inputClause or outputClause
    const target = this.getAllowedValuesTarget();
    this.setState({
      values
    });
    this._modeling.editAllowedValues(target, values && getValuesArray(values));
  };
  onListChange = values => {
    this.setPredefinedValues(values);
  };
  getAllowedValuesTarget() {
    const element = this.getElement();
    if (is(element, 'dmn:LiteralExpression')) {
      return element.$parent;
    } else {
      return element;
    }
  }
  onInput = ({
    isValid,
    value
  }) => {
    this.setState({
      inputValue: value
    });
  };

  /**
   * Add new value on ENTER.
   */
  onKeyDown = ({
    isValid,
    event
  }) => {
    if (!isEnter(event.keyCode)) {
      return;
    }
    event.stopPropagation();
    event.preventDefault();
    if (isValid) {
      const {
        inputValue,
        values
      } = this.state;
      const parsedString = parseString(inputValue);
      this.onListChange((values || []).concat(parsedString.values.map(value => {
        return {
          value,
          isCheckable: false,
          isRemovable: true,
          group: this._translate('Predefined values')
        };
      })));
      this.setState({
        inputValue: ''
      });
    }
  };
  handleRemovePredifinedValuesClick = e => {
    e.stopPropagation();
    this.removePredefinedValues();
  };
  removePredefinedValues = () => {
    this.setPredefinedValues(null);
  };
  getElement() {
    return this.props.context.output || this.props.context.input.inputExpression;
  }
  render() {
    const element = this.getElement();
    const {
      inputValue,
      values
    } = this.state;
    return element.typeRef === 'string' ? createVNode(1, "div", "context-menu-container allowed-values-edit", createVNode(1, "div", "dms-form-control", [!isNull(values) && values.length > 0 && createComponentVNode(2, List, {
      "labelComponent": Label,
      "items": values,
      "onChange": this.onListChange
    }), !isNull(values) && !values.length && createVNode(1, "div", null, [createVNode(1, "label", "dms-label", this._translate('Predefined values'), 0), createVNode(1, "span", "placeholder", this._translate('No values'), 0)], 4), !isNull(values) && createVNode(1, "p", "dms-hint", createVNode(1, "button", "del-values", this._translate('Clear predefined values'), 0, {
      "type": "button",
      "onClick": this.handleRemovePredifinedValuesClick
    }), 2), createVNode(1, "label", "dms-label", this._translate('Add predefined values'), 0), createComponentVNode(2, ValidatedInput, {
      "onInput": this.onInput,
      "onKeyDown": this.onKeyDown,
      "placeholder": this._translate('"value", "value", ...'),
      "type": "text",
      "validate": value => {
        if (!parseString(value)) {
          return this._translate('Strings must be in double quotes');
        }
      },
      "value": inputValue
    })], 0), 2) : null;
  }
}
function Label(label) {
  return createVNode(1, "label", "dms-label", label, 0);
}

// helpers //////////////////////

function isEnter(keyCode) {
  return keyCode === 13;
}
function isNull(value) {
  return value === null;
}
//# sourceMappingURL=AllowedValuesEditing.js.map
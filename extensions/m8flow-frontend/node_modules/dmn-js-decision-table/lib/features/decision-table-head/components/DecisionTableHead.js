import { createVNode } from "inferno";
import { is, getBusinessObject } from 'dmn-js-shared/lib/util/ModelUtil';
import { Component } from 'inferno';
import { mixin } from 'table-js/lib/components';
import { ComponentWithSlots } from 'dmn-js-shared/lib/components/mixins';
export default class DecisionTableHead extends Component {
  constructor(props, context) {
    super(props, context);
    mixin(this, ComponentWithSlots);
    this._sheet = context.injector.get('sheet');
    this._changeSupport = context.changeSupport;
  }
  onElementsChanged = () => {
    this.forceUpdate();
  };
  componentWillMount() {
    const root = this._sheet.getRoot();
    this._changeSupport.onElementsChanged(root.id, this.onElementsChanged);
  }
  componentWillUnmount() {
    const root = this._sheet.getRoot();
    this._changeSupport.offElementsChanged(root.id, this.onElementsChanged);
  }
  render() {
    const root = this._sheet.getRoot();
    if (!is(root, 'dmn:DMNElement')) {
      return null;
    }
    const businessObject = getBusinessObject(root);
    const inputs = businessObject.input,
      outputs = businessObject.output;
    return createVNode(1, "thead", null, createVNode(1, "tr", null, [createVNode(1, "th", "index-column"), this.slotFills({
      type: 'cell',
      context: {
        cellType: 'before-label-cells'
      }
    }), inputs && inputs.map((input, index) => {
      const width = input.width || '192px';
      return this.slotFill({
        type: 'cell',
        context: {
          cellType: 'input-header',
          input,
          index,
          inputsLength: inputs.length,
          width
        },
        key: input.id
      }, DefaultInputHeaderCell);
    }), outputs.map((output, index) => {
      return this.slotFill({
        type: 'cell',
        context: {
          cellType: 'output-header',
          output,
          index,
          outputsLength: outputs.length
        },
        key: output.id
      }, DefaultOutputHeaderCell);
    }), this.slotFills({
      type: 'cell',
      context: {
        cellType: 'after-label-cells'
      }
    })], 0), 2);
  }
}

// default components ///////////////////////

function DefaultInputHeaderCell(props, context) {
  const {
    input,
    className,
    index
  } = props;
  const {
    label,
    inputExpression,
    inputValues
  } = input;
  const translate = context.injector.get('translate');
  const actualClassName = (className || '') + ' input-cell';
  return createVNode(1, "th", actualClassName, [createVNode(1, "div", "clause", index === 0 ? translate('When') : translate('And'), 0), label ? createVNode(1, "div", "input-label", label, 0, {
    "title": translate('Input label: ') + label
  }) : createVNode(1, "div", "input-expression", inputExpression.text, 0, {
    "title": translate('Input expression: ') + inputExpression.text
  }), createVNode(1, "div", "input-variable", inputValues && inputValues.text || inputExpression.typeRef, 0, {
    "title": inputValues && inputValues.text ? translate('Input values') : translate('Input type')
  })], 0, {
    "data-col-id": input.id
  }, input.id);
}
function DefaultOutputHeaderCell(props, context) {
  const {
    output,
    className,
    index
  } = props;
  const {
    label,
    name,
    outputValues,
    typeRef
  } = output;
  const translate = context.injector.get('translate');
  const actualClassName = (className || '') + ' output-cell';
  return createVNode(1, "th", actualClassName, [createVNode(1, "div", "clause", index === 0 ? translate('Then') : translate('And'), 0), label ? createVNode(1, "div", "output-label", label, 0, {
    "title": translate('Output label')
  }) : createVNode(1, "div", "output-name", name, 0, {
    "title": translate('Output name')
  }), createVNode(1, "div", "output-variable", outputValues && outputValues.text || typeRef, 0, {
    "title": outputValues && outputValues.text ? translate('Output values') : translate('Output type')
  })], 0, null, output.id);
}
//# sourceMappingURL=DecisionTableHead.js.map
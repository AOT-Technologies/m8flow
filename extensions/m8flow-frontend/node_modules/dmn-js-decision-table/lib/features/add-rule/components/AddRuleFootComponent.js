import { createVNode, createTextVNode } from "inferno";
import { Component } from 'inferno';
import { inject } from 'table-js/lib/components';
export default class AddRuleFootComponent extends Component {
  constructor(props, context) {
    super(props, context);
    inject(this);
    this.addRule = this.addRule.bind(this);
  }
  componentWillMount() {
    this._eventBus = this.context.injector.get('eventBus');
  }
  handleClick = e => {
    e.stopPropagation();
    this.addRule(e.target.dataset.colIndex);
  };
  addRule(colIndex) {
    this._eventBus.fire('addRule', {
      colIndex
    });
  }
  render() {
    const {
      cols
    } = this.props;
    const cells = [createVNode(1, "td", "add-rule-add", createVNode(1, "button", "dmn-icon-plus action-icon", null, 1, {
      "title": this.translate('Add rule')
    }), 2)];
    const {
      businessObject
    } = this.sheet.getRoot();
    if (!businessObject.input || !businessObject.input.length) {
      cells.push(createVNode(1, "td", "input-cell", createTextVNode("-"), 2));
    }
    for (let i = 0; i < cols.length + 1; i++) {
      let className = 'add-rule';
      const businessObject = cols[i] && cols[i].businessObject;
      let placeholder = '';
      if (businessObject) {
        if (businessObject.$instanceOf('dmn:InputClause')) {
          className += ' input-cell';
          placeholder = '-';
        }
        if (businessObject.$instanceOf('dmn:OutputClause')) {
          className += ' output-cell';
        }
      } else {
        className += ' annotation';
      }
      cells.push(createVNode(1, "td", className, placeholder, 0, {
        "data-col-index": i
      }));
    }
    return createVNode(1, "tfoot", "actionable add-rule", createVNode(1, "tr", null, cells, 0), 2, {
      "onClick": this.handleClick
    });
  }
}
AddRuleFootComponent.$inject = ['sheet', 'translate'];
//# sourceMappingURL=AddRuleFootComponent.js.map
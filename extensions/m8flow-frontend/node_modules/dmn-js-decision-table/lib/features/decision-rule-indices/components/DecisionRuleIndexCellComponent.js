import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
export default class DecisionRulesIndexCellComponent extends Component {
  render() {
    const {
      row,
      rowIndex
    } = this.props;
    const {
      components
    } = this.context;
    const innerComponents = components.getComponents('cell-inner', {
      cellType: 'rule-index',
      row,
      rowIndex
    });
    return createVNode(1, "td", "rule-index", [innerComponents && innerComponents.map(InnerComponent => createComponentVNode(2, InnerComponent, {
      "row": row,
      "rowIndex": rowIndex
    })), rowIndex + 1], 0, {
      "data-element-id": row.id,
      "data-row-id": row.id
    });
  }
}
//# sourceMappingURL=DecisionRuleIndexCellComponent.js.map
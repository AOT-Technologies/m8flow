import { createComponentVNode } from "inferno";
import { Component } from 'inferno';
import { Cell } from 'table-js/lib/components';
import { is } from 'dmn-js-shared/lib/util/ModelUtil';
export default class DecisionRulesCellComponent extends Component {
  render() {
    const {
      cell,
      row,
      col
    } = this.props;
    if (is(cell, 'dmn:UnaryTests')) {
      return createComponentVNode(2, Cell, {
        "className": "input-cell",
        "elementId": cell.id,
        "data-row-id": row.id,
        "data-col-id": col.id,
        children: cell.businessObject.text
      });
    } else {
      return createComponentVNode(2, Cell, {
        "className": "output-cell",
        "elementId": cell.id,
        "data-row-id": row.id,
        "data-col-id": col.id,
        children: cell.businessObject.text
      });
    }
  }
}
//# sourceMappingURL=DecisionRulesCellComponent.js.map
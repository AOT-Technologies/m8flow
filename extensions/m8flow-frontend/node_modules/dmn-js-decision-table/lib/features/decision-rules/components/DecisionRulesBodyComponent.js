import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
export default class DecisionRulesBodyComponent extends Component {
  render({
    rows,
    cols
  }) {
    const {
      components
    } = this.context;
    return createVNode(1, "tbody", null, rows.map((row, rowIndex) => {
      const RowComponent = components.getComponent('row', {
        rowType: 'rule'
      });
      return RowComponent && createComponentVNode(2, RowComponent, {
        "row": row,
        "rowIndex": rowIndex,
        "cols": cols
      }, row.id);
    }), 0);
  }
}
//# sourceMappingURL=DecisionRulesBodyComponent.js.map
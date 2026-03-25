import { createVNode } from "inferno";
import { Component } from 'inferno';
export default class DecisionPropertiesComponent extends Component {
  constructor(props, context) {
    super(props, context);
    this._viewer = context.injector.get('viewer');
  }
  render() {
    // there is only one single element
    const {
      name
    } = this._viewer.getDecision();
    return createVNode(1, "div", "decision-properties", createVNode(1, "h3", "decision-name", name, 0), 2);
  }
}
//# sourceMappingURL=DecisionPropertiesComponent.js.map
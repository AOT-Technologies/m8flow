import { createVNode } from "inferno";
import { Component } from 'inferno';
export default class TextareaComponent extends Component {
  constructor(props, context) {
    super(props, context);
    this._viewer = context.injector.get('viewer');
  }
  render() {
    const {
      text
    } = this._viewer.getDecision().decisionLogic;
    return createVNode(1, "div", "textarea", createVNode(1, "div", "content", text, 0), 2);
  }
}
//# sourceMappingURL=TextareaComponent.js.map
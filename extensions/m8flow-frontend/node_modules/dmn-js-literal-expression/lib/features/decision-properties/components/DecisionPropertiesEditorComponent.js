import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
import EditableComponent from 'dmn-js-shared/lib/components/EditableComponent';
export default class DecisionPropertiesEditorComponent extends Component {
  constructor(props, context) {
    super(props, context);
    this._viewer = context.injector.get('viewer');
    this._modeling = context.injector.get('modeling');
    this._translate = context.injector.get('translate');
    this.setupChangeListeners({
      bind: this.getDecision().id
    });
  }
  componentWillUnmount() {
    this.setupChangeListeners({
      unbind: this.getDecision().id
    });
  }
  getDecision() {
    return this._viewer.getDecision();
  }
  onElementsChanged = () => {
    this.forceUpdate();
  };
  setupChangeListeners({
    bind,
    unbind
  }) {
    const {
      changeSupport
    } = this.context;
    if (typeof unbind === 'string') {
      changeSupport.offElementsChanged(unbind, this.onElementsChanged);
    }
    if (typeof bind === 'string') {
      changeSupport.onElementsChanged(bind, this.onElementsChanged);
    }
  }
  setDecisionName = name => {
    this._modeling.editDecisionName(name);
  };
  render() {
    const {
      name
    } = this.getDecision();
    return createVNode(1, "header", "decision-properties", createComponentVNode(2, DecisionName, {
      "label": this._translate('Decision name'),
      "className": "decision-name editor",
      "value": name,
      "onBlur": resetScroll,
      "onChange": this.setDecisionName
    }), 2);
  }
}
class DecisionName extends EditableComponent {
  render() {
    return createVNode(1, "h3", this.getClassName(), this.getEditor(), 0);
  }
}
function resetScroll(event) {
  event.target.scroll(0, 0);
}
//# sourceMappingURL=DecisionPropertiesEditorComponent.js.map
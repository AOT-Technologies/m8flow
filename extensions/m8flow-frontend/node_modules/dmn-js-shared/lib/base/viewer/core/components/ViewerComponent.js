import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
export default class ViewerComponent extends Component {
  constructor(props) {
    super(props);
    const injector = this._injector = props.injector;
    this._changeSupport = injector.get('changeSupport');
    this._components = injector.get('components');
    this._renderer = injector.get('renderer');
  }
  getChildContext() {
    return {
      changeSupport: this._changeSupport,
      components: this._components,
      renderer: this._renderer,
      injector: this._injector
    };
  }
  render() {
    const components = this._components.getComponents('viewer');
    return createVNode(1, "div", "viewer-container", components && components.map((Component, index) => createComponentVNode(2, Component, null, index)), 0);
  }
}
//# sourceMappingURL=ViewerComponent.js.map
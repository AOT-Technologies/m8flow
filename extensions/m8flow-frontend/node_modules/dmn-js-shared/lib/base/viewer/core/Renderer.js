import { createComponentVNode } from "inferno";
import { render } from 'inferno';
import ViewerComponent from './components/ViewerComponent';
export default class Renderer {
  constructor(changeSupport, components, config, eventBus, injector) {
    const {
      container
    } = config;
    this._container = container;
    eventBus.on('renderer.mount', () => {
      render(createComponentVNode(2, ViewerComponent, {
        "injector": injector
      }), container);
    });
    eventBus.on('renderer.unmount', () => {
      render(null, container);
    });
  }
  getContainer() {
    return this._container;
  }
}
Renderer.$inject = ['changeSupport', 'components', 'config.renderer', 'eventBus', 'injector'];
//# sourceMappingURL=Renderer.js.map
import { createVNode, createComponentVNode } from "inferno";
export class ViewRenderer {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('viewer', () => {
      return Header;
    });
    components.onGetComponent('viewer', () => {
      return Body;
    });
    components.onGetComponent('viewer', () => {
      return Footer;
    });
  }
}
function Header(_, {
  injector
}) {
  const components = injector.get('components');
  const headerComponents = components.getComponents('header');
  return createVNode(1, "div", "dmn-boxed-expression-section dmn-boxed-expression-header", headerComponents && headerComponents.map((Component, index) => {
    return createComponentVNode(2, Component, null, index);
  }), 0);
}
function Body(_, {
  injector
}) {
  const components = injector.get('components');
  const bodyComponents = components.getComponents('body');
  return createVNode(1, "div", "dmn-boxed-expression-section dmn-boxed-expression-body", bodyComponents && bodyComponents.map((Component, index) => {
    return createComponentVNode(2, Component, null, index);
  }), 0);
}
function Footer(_, {
  injector
}) {
  const components = injector.get('components');
  const footerComponents = components.getComponents('footer');
  return createVNode(1, "div", "dmn-boxed-expression-section dmn-boxed-expression-footer", footerComponents && footerComponents.map((Component, index) => {
    return createComponentVNode(2, Component, null, index);
  }), 0);
}
//# sourceMappingURL=ViewRenderer.js.map
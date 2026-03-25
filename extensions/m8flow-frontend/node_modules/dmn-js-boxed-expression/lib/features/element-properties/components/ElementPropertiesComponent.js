import { createVNode } from "inferno";
export default function ElementPropertiesComponent(_, context) {
  const viewer = context.injector.get('viewer');

  // there is only one single element
  const {
    name
  } = viewer.getRootElement();
  return createVNode(1, "div", "element-properties", createVNode(1, "h2", "element-name", name, 0), 2);
}
//# sourceMappingURL=ElementPropertiesComponent.js.map
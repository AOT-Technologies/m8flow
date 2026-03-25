import { createVNode, createComponentVNode } from "inferno";
/**
 * Allows to use modules from `table-js` which depend on `table.*` components.
 * @TODO(barmac): This is a temporary solution until we move context menu out of table-js.
 */
export class TableJsSupport {
  static $inject = ['components'];
  constructor(components) {
    components.onGetComponent('viewer', () => {
      const children = components.getComponents('table.before') || [];
      return () => {
        return createVNode(1, "div", null, children.map((Component, index) => createComponentVNode(2, Component, null, index)), 0);
      };
    });
  }
}
//# sourceMappingURL=TableJsSupport.js.map
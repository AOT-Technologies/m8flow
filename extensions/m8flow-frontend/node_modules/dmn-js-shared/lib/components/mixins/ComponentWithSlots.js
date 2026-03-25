import { createComponentVNode, normalizeProps } from "inferno";
/**
 * A simple slot extension, built upon the components service.
 *
 * @type {Object}
 */
const ComponentWithSlots = {
  slotFill(slotProps, DefaultFill) {
    const {
      type,
      context,
      ...props
    } = slotProps;
    const Fill = this.components.getComponent(type, context) || DefaultFill;
    if (Fill) {
      return normalizeProps(createComponentVNode(2, Fill, {
        ...context,
        ...props
      }));
    }
    return null;
  },
  slotFills(slotProps) {
    const {
      type,
      context,
      ...props
    } = slotProps;
    const fills = this.components.getComponents(type, context);
    return fills.map(Fill => normalizeProps(createComponentVNode(2, Fill, {
      ...context,
      ...props
    })));
  }
};
export default ComponentWithSlots;
ComponentWithSlots.$inject = ['components'];
//# sourceMappingURL=ComponentWithSlots.js.map
import { createVNode } from "inferno";
export function EditButton({
  label,
  onClick
}) {
  return createVNode(1, "button", "edit-button dmn-icon-edit", null, 1, {
    "aria-label": label,
    "type": "button",
    "onClick": onClick
  });
}
//# sourceMappingURL=EditButton.js.map
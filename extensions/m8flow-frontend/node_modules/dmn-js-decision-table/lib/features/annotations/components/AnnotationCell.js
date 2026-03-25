import { createComponentVNode } from "inferno";
import { Cell } from 'table-js/lib/components';
export default function AnnotationCell(props) {
  const {
    row
  } = props;
  const {
    id,
    description
  } = row.businessObject;
  return createComponentVNode(2, Cell, {
    "className": "annotation",
    "elementId": id,
    children: description || '-'
  });
}
//# sourceMappingURL=AnnotationCell.js.map
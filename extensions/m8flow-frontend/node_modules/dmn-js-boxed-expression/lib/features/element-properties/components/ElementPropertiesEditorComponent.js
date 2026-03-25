import { createVNode, createComponentVNode } from "inferno";
import Input from 'dmn-js-shared/lib/components/Input';
import { withChangeSupport } from '../../../util/withChangeSupport';
const ElementName = withChangeSupport(function (props, context) {
  const {
    element
  } = props;
  const modeling = context.injector.get('modeling');
  const translate = context.injector.get('translate');
  const name = element.get('name');
  const onChange = name => {
    modeling.updateProperties(element, {
      name
    });
  };
  return createComponentVNode(2, Input, {
    "label": translate('Element name'),
    "className": "element-name editor",
    "value": name,
    "onChange": onChange
  });
}, props => [props.element]);
export default function ElementPropertiesEditorComponent(_, context) {
  const viewer = context.injector.get('viewer');
  const rootElement = viewer.getRootElement();
  return createVNode(1, "div", "element-properties", createComponentVNode(2, ElementName, {
    "element": rootElement
  }), 2);
}
//# sourceMappingURL=ElementPropertiesEditorComponent.js.map
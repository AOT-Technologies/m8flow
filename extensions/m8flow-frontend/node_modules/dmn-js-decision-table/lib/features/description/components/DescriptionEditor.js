import { createVNode, createComponentVNode } from "inferno";
import { Component } from 'inferno';
import { isString } from 'min-dash';
import { query as domQuery } from 'min-dom';
import EditableComponent from 'dmn-js-shared/lib/components/EditableComponent';
export default class DescriptionEditor extends Component {
  constructor(props, context) {
    super(props, context);
    this._elementRegistry = context.injector.get('elementRegistry');
    this._modeling = context.injector.get('modeling');
    this._changeSupport = this.context.changeSupport;
    const {
      id
    } = this.props.context;
    this._element = this._elementRegistry.get(id);
  }
  onElementsChanged = () => {
    this.forceUpdate();
  };
  componentWillMount() {
    if (this._element) {
      this._changeSupport.onElementsChanged(this._element.id, this.onElementsChanged);
    }
  }
  componentDidMount() {
    const {
      autoFocus
    } = this.props.context;
    if (autoFocus && this.node) {
      const editor = getEditor(this.node);
      editor.focus();
    }
  }
  componentWillUnmount() {
    if (this._element) {
      this._changeSupport.offElementsChanged(this._element.id, this.onElementsChanged);
      const {
        businessObject
      } = this._element;
      const {
        description
      } = businessObject;

      // if empty description remove description
      if (isString(description) && !description.length) {
        this.changeDescription(null);
      }
    }
  }
  changeDescription = value => {
    this._modeling.updateProperties(this._element, {
      description: value
    });
  };
  render() {
    if (!this._element) {
      return;
    }
    const {
      businessObject
    } = this._element;
    const {
      description
    } = businessObject;
    if (!isString(description)) {
      return;
    }
    return createVNode(1, "div", "context-menu-container description-editor", createComponentVNode(2, Editor, {
      "className": "dms-input",
      "onChange": this.changeDescription,
      "value": description
    }), 2, null, null, node => this.node = node);
  }
}
class Editor extends EditableComponent {
  render() {
    return createVNode(1, "div", this.getClassName(), this.getEditor(), 0);
  }
}

// helpers //////////

function getEditor(container) {
  return domQuery('.content-editable', container);
}
//# sourceMappingURL=DescriptionEditor.js.map
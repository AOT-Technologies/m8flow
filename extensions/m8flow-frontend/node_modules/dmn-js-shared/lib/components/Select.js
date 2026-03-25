import { createVNode } from "inferno";
import { Component } from 'inferno';
export default class Select extends Component {
  constructor(props, context) {
    super(props, context);
    const {
      value
    } = props;
    this.state = {
      value
    };
  }
  componentWillReceiveProps(props) {
    const {
      value
    } = props;
    this.setState({
      value
    });
  }
  onChange = event => {
    const {
      value
    } = event.target;
    this.setState({
      value
    });
    const {
      onChange
    } = this.props;
    if (typeof onChange !== 'function') {
      return;
    }
    onChange(value);
  };
  render() {
    const {
      className,
      label,
      options
    } = this.props;
    const {
      value
    } = this.state;
    return createVNode(256, "select", [className || '', 'dms-select'].join(' '), (options || []).map(({
      label,
      value
    }) => {
      return createVNode(1, "option", "option", label, 0, {
        "value": value
      });
    }), 0, {
      "aria-label": label,
      "onChange": this.onChange,
      "value": value
    });
  }
}
//# sourceMappingURL=Select.js.map
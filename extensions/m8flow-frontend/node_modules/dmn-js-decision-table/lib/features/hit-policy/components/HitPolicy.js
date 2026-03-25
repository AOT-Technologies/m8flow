import { createVNode } from "inferno";
import { Component } from 'inferno';
import { inject } from 'table-js/lib/components';
import { HIT_POLICIES } from './../HitPolicies';
import { find } from 'min-dash';
export default class HitPolicy extends Component {
  constructor(props, context) {
    super(props, context);
    this._translate = context.injector.get('translate');
    inject(this);
  }
  getRoot() {
    return this.sheet.getRoot();
  }
  render() {
    const root = this.getRoot(),
      businessObject = root.businessObject;
    const {
      aggregation,
      hitPolicy
    } = businessObject;
    const hitPolicyEntry = find(HIT_POLICIES, entry => {
      return isEqualHitPolicy(entry.value, {
        aggregation,
        hitPolicy
      });
    });
    return createVNode(1, "div", "hit-policy header", [createVNode(1, "label", "dms-label", this._translate('Hit policy:'), 0), createVNode(1, "span", "hit-policy-value", this._translate(hitPolicyEntry.label), 0)], 4, {
      "title": this._translate(hitPolicyEntry.explanation)
    });
  }
}
HitPolicy.$inject = ['sheet'];

// helpers //////////////////////
function isEqualHitPolicy(a, b) {
  return a.hitPolicy === b.hitPolicy && a.aggregation === b.aggregation;
}
//# sourceMappingURL=HitPolicy.js.map
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DmnCanvas } from './DmnCanvas';

/** Minimal DRD: one decision with DMNDI, as the modeler receives it. */
const DMN_XML = `<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" xmlns:dmndi="https://www.omg.org/spec/DMN/20191111/DMNDI/" xmlns:dc="http://www.omg.org/spec/DMN/20180521/DC/" id="Definitions_1" name="DRD" namespace="https://m8flow.example/dmn">
  <decision id="check_approval_route" name="Check Approval Route">
    <decisionTable id="DecisionTable_1">
      <input id="Input_1">
        <inputExpression id="InputExpression_1" typeRef="string"><text></text></inputExpression>
      </input>
      <output id="Output_1" typeRef="string" />
    </decisionTable>
  </decision>
  <dmndi:DMNDI>
    <dmndi:DMNDiagram id="DMNDiagram_1">
      <dmndi:DMNShape id="DMNShape_1" dmnElementRef="check_approval_route">
        <dc:Bounds height="80" width="180" x="157" y="151" />
      </dmndi:DMNShape>
    </dmndi:DMNDiagram>
  </dmndi:DMNDI>
</definitions>`;

describe('DmnCanvas', () => {
  // M8F-510: DmnModeler used `inherits()` + `.call(this)` against dmn-js's ES
  // class Modeler, so constructing it threw inside the mount effect. With no
  // error boundary above it, React unmounted the whole app -- the modeler page
  // rendered completely blank for every .dmn file.
  it('constructs the DMN modeler without throwing out of the mount effect', async () => {
    const { container } = render(<DmnCanvas xml={DMN_XML} />);

    // The canvas container survives the effect and dmn-js mounts into it.
    await waitFor(() => {
      expect(container.querySelector('.dmn-js-parent')).toBeTruthy();
    });
  });
});

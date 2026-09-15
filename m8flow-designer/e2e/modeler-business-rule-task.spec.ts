import { expect, test } from '@playwright/test';

import { editorCredentials, signInAsSharedRealmUser } from './helpers/auth';
import { openPropertiesPanelGroup, selectElement } from './helpers/diagram';
import { seedModelerPath } from './helpers/fixtures';
import { seedProcessModelFile } from './helpers/seedFixture';

/**
 * Phase 2 — Business Rule Task / DMN wiring (phased Task Configuration
 * Parity plan, §Phase 2). Implemented: BpmnCanvas.tsx now answers
 * `spiff.dmn_files.requested` (from the process model's own file list,
 * filtered to `.dmn` — same pattern as Phase 1's JSON Schema Filename field)
 * and `spiff.dmn.edit` (navigates to the chosen .dmn file's own modeler
 * page — a genuine improvement over m8flow-frontend, whose one real
 * consumer leaves `onLaunchDmnEditor` a no-op).
 *
 * Own fixture files — the seed model has neither a bpmn:BusinessRuleTask nor
 * a .dmn file, so this phase seeds both (a BPMN file referencing the
 * decision, and the decision table itself) into the shared seed model
 * directory. Never touches SEED_PRIMARY_FILE or another phase's file.
 */
const PHASE2_BPMN_FILE = 'phase2-business-rule-task.bpmn';
const PHASE2_DMN_FILE = 'phase2-decision.dmn';
const BUSINESS_RULE_TASK_ID = 'Activity_decide';

const PHASE2_BPMN_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                   id="Definitions_phase2" targetNamespace="http://m8flow.org/e2e/phase2">
  <bpmn:process id="Process_phase2" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:businessRuleTask id="${BUSINESS_RULE_TASK_ID}" name="Decide" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="${BUSINESS_RULE_TASK_ID}" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="${BUSINESS_RULE_TASK_ID}" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_phase2">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="150" y="150" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_decide_di" bpmnElement="${BUSINESS_RULE_TASK_ID}">
        <dc:Bounds x="250" y="128" width="100" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="420" y="150" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_1_di" bpmnElement="Flow_1">
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="186" y="168" />
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="250" y="168" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_2_di" bpmnElement="Flow_2">
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="350" y="168" />
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="420" y="168" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;

const PHASE2_DMN_XML = `<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             xmlns:dmndi="https://www.omg.org/spec/DMN/20191111/DMNDI/"
             xmlns:dc="http://www.omg.org/spec/DMN/20180521/DC/"
             id="Definitions_phase2_dmn" name="Approval Decision"
             namespace="http://m8flow.org/e2e/phase2">
  <decision id="Decision_1" name="Approval Decision">
    <decisionTable id="DecisionTable_1">
      <input id="Input_1" label="Amount">
        <inputExpression id="InputExpression_1" typeRef="number">
          <text>amount</text>
        </inputExpression>
      </input>
      <output id="Output_1" label="Approved" typeRef="boolean" />
      <rule id="Rule_1">
        <inputEntry id="InputEntry_1"><text>&lt; 100</text></inputEntry>
        <outputEntry id="OutputEntry_1"><text>true</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
  <dmndi:DMNDI>
    <dmndi:DMNDiagram>
      <dmndi:DMNShape dmnElementRef="Decision_1">
        <dc:Bounds height="80" width="180" x="160" y="100" />
      </dmndi:DMNShape>
    </dmndi:DMNDiagram>
  </dmndi:DMNDI>
</definitions>`;

test.describe('m8flow-designer Process Modeler — Business Rule Task / DMN wiring (Phase 2)', () => {
  test.beforeEach(async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await seedProcessModelFile(page, PHASE2_DMN_FILE, PHASE2_DMN_XML);
    await seedProcessModelFile(page, PHASE2_BPMN_FILE, PHASE2_BPMN_XML);
    await page.goto(seedModelerPath(PHASE2_BPMN_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, BUSINESS_RULE_TASK_ID);
  });

  test('Select Decision Table dropdown lists .dmn files from this process model', async ({
    page,
  }) => {
    const group = await openPropertiesPanelGroup(page, 'business_rule_properties');
    const select = group.getByLabel('Select Decision Table');
    const optionLabels = await select.locator('option').allTextContents();
    expect(optionLabels).toContain(PHASE2_DMN_FILE);
  });

  test('"Launch Editor" for the decision table navigates into that .dmn file\'s modeler', async ({
    page,
  }) => {
    const group = await openPropertiesPanelGroup(page, 'business_rule_properties');
    await group.getByLabel('Select Decision Table').selectOption(PHASE2_DMN_FILE);
    await group.getByRole('button', { name: 'Launch Editor' }).click();

    await expect(page).toHaveURL(new RegExp(`modeler/${PHASE2_DMN_FILE}$`));
    // A real DMN diagram loaded, not just a URL change — dmn-js's own DRD
    // canvas renders the decision table shape.
    await expect(page.locator('.djs-container')).toBeVisible();
    await page.getByTitle('Zoom in').click();
    await page.getByTitle('Zoom out').click();
    await page.getByTitle('Fit to viewport').click();
    await expect(page.getByTitle('Zoom in')).toBeVisible();
  });
});

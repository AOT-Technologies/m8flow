import { expect, test } from '@playwright/test';

import { editorCredentials, signInAsSharedRealmUser } from './helpers/auth';
import { openPropertiesPanelGroup, selectElement } from './helpers/diagram';
import { seedModelerPath } from './helpers/fixtures';
import { seedProcessModelFile } from './helpers/seedFixture';

/**
 * Service Task connector wiring. BpmnCanvas answers
 * `spiff.service_tasks.requested` from `GET /connectors-grouped`, flattened
 * to `{id, parameters}[]`. An empty catalog is an honest Action-tab empty
 * state (not a blank Operator ID <select>); a live HTTP V2 catalog still
 * round-trips into the Parameters tab.
 */
const PHASE4_FILE = 'phase4-service-task.bpmn';
const SERVICE_TASK_ID = 'Activity_send_email';

const PHASE4_DIAGRAM_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                   id="Definitions_phase4" targetNamespace="http://m8flow.org/e2e/phase4">
  <bpmn:process id="Process_phase4" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:serviceTask id="${SERVICE_TASK_ID}" name="Send Email" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="${SERVICE_TASK_ID}" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="${SERVICE_TASK_ID}" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_phase4">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="150" y="150" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_send_email_di" bpmnElement="${SERVICE_TASK_ID}">
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

/** How many total operations the live backend currently offers, across every connector. */
async function fetchRealOperationCount(page: import('@playwright/test').Page): Promise<number> {
  const response = await page.request.get('/v1.0/m8flow/connectors-grouped');
  const groups: Array<{ operations: unknown[] }> = await response.json();
  return groups.reduce((sum, g) => sum + g.operations.length, 0);
}

test.describe('m8flow-designer Process Modeler — Service Task connector wiring (Phase 4)', () => {
  test.beforeEach(async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await seedProcessModelFile(page, PHASE4_FILE, PHASE4_DIAGRAM_XML);
    await page.goto(seedModelerPath(PHASE4_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, SERVICE_TASK_ID);
  });

  test('the Action tab reflects the live connector catalog', async ({ page }) => {
    const expectedCount = await fetchRealOperationCount(page);
    const group = await openPropertiesPanelGroup(page, 'service_task_properties');

    if (expectedCount === 0) {
      await expect(
        group.getByText(/no connector operators are available/i),
      ).toBeVisible();
      await expect(group.getByLabel('Operator ID')).toHaveCount(0);
      return;
    }

    const select = group.getByLabel('Operator ID');
    await expect(select).toBeVisible();
    await expect(select.locator('option')).toHaveCount(expectedCount);
  });

  test('selecting an operator renders its own parameter fields', async ({ page }) => {
    const expectedCount = await fetchRealOperationCount(page);
    test.skip(expectedCount === 0, 'connector-proxy catalog is empty in this environment');

    const group = await openPropertiesPanelGroup(page, 'service_task_properties');
    const select = group.getByLabel('Operator ID');
    await expect(select).toBeVisible();
    const operatorId = await select.locator('option').evaluateAll((opts) =>
      opts.map((option) => (option as HTMLOptionElement).value).find((value) => value !== ''),
    );
    expect(operatorId).toBeTruthy();
    await select.selectOption(operatorId!);
    await group.getByRole('tab', { name: 'Parameters' }).click();
    await expect(group.locator('.m8flow-service-task-param-row')).not.toHaveCount(0);
  });

  test('the service task group stays open across the async connector-list round trip', async ({
    page,
  }) => {
    // `open` lives on the group's *header* element, not the group root
    // itself (confirmed live — @bpmn-io/properties-panel's own DOM, same
    // convention openPropertiesPanelGroup's internal check already uses).
    const group = await openPropertiesPanelGroup(page, 'service_task_properties');
    await page.waitForTimeout(500);
    await expect(group.locator(':scope > .bio-properties-panel-group-header')).toHaveClass(/open/);
  });
});

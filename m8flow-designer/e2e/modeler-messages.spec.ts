import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useMockProcessModel } from './helpers/mockCatalog';
import { openChangeElementMenu, openPropertiesPanelGroup, selectElement } from './helpers/diagram';
import { seedModelerPath } from './helpers/fixtures';
import { seedProcessModelFile } from './helpers/seedFixture';

/**
 * Message events and process-level message models are dropped. Send/Receive
 * Task still keep the element-level `messages` group (catalog allows those
 * task types). Do not assert message-model persist, Add Message, or schema
 * Launch Editor for a message.
 */
const PHASE5_FILE = 'phase5-messages.bpmn';
const SEND_TASK_ID = 'Activity_notify';

const PHASE5_DIAGRAM_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                   id="Definitions_phase5" targetNamespace="http://m8flow.org/e2e/phase5">
  <bpmn:process id="Process_phase5" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:sendTask id="${SEND_TASK_ID}" name="Notify" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="${SEND_TASK_ID}" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="${SEND_TASK_ID}" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_phase5">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="150" y="150" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_notify_di" bpmnElement="${SEND_TASK_ID}">
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

// Creates the mock process model before these tests and deletes it after.
useMockProcessModel(test);

test.describe('Process Modeler: Message settings', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await seedProcessModelFile(page, PHASE5_FILE, PHASE5_DIAGRAM_XML);
    await page.goto(seedModelerPath(PHASE5_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  });

  test('A start event cannot be changed into a message start event', async ({ page }) => {
    const menu = await openChangeElementMenu(page, 'StartEvent_1');
    await expect(menu.locator('[data-id="replace-with-message-start"]')).toHaveCount(0);
    await expect(menu.locator('[data-id="replace-with-non-interrupting-message-start"]')).toHaveCount(0);
    console.log('Start event cannot be changed into a message start event.');
  });

  test('Process-wide Messages and Correlation settings are not shown', async ({ page }) => {
    await page.locator('.djs-container').click({ position: { x: 8, y: 8 } });
    await expect(page.locator('.bio-properties-panel-group[data-group-id="group-messages"]')).toHaveCount(0);
    await expect(
      page.locator('.bio-properties-panel-group[data-group-id="group-correlation_properties"]'),
    ).toHaveCount(0);
    console.log('Process-wide Messages and Correlation settings are hidden.');
  });

  test('A Send Task still shows its Messages settings', async ({ page }) => {
    await selectElement(page, SEND_TASK_ID);
    const group = await openPropertiesPanelGroup(page, 'messages');
    await expect(group).toBeVisible();
    console.log('Send Task still shows its Messages settings.');
  });
});

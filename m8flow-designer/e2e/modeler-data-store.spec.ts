import { expect, test } from '@playwright/test';

import { editorCredentials, signInAsSharedRealmUser } from './helpers/auth';
import { openChangeElementMenu, paletteEntry, selectElement } from './helpers/diagram';
import { seedModelerPath } from './helpers/fixtures';
import { seedProcessModelFile } from './helpers/seedFixture';

/**
 * Data-store persist is dropped. Palette and replace menu must not offer a
 * data store; the properties group is stripped. The fixture is a persistable
 * data object (keep-scope) so we never PUT a DataStoreReference.
 */
const GUARD_FILE = 'checklist-data-object.bpmn';
const DATA_OBJECT_ID = 'DataObjectReference_1';

const GUARD_DIAGRAM_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                   id="Definitions_data_object" targetNamespace="http://m8flow.org/e2e/data-object">
  <bpmn:process id="Process_data_object" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:task id="Activity_1" name="Work" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:dataObject id="DataObject_1" />
    <bpmn:dataObjectReference id="${DATA_OBJECT_ID}" name="Doc" dataObjectRef="DataObject_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Activity_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Activity_1" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_data_object">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="150" y="150" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_1_di" bpmnElement="Activity_1">
        <dc:Bounds x="250" y="128" width="100" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="420" y="150" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="${DATA_OBJECT_ID}_di" bpmnElement="${DATA_OBJECT_ID}">
        <dc:Bounds x="277" y="250" width="36" height="50" />
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

test.describe('m8flow-designer Process Modeler — Data Store guard', () => {
  test.beforeEach(async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await seedProcessModelFile(page, GUARD_FILE, GUARD_DIAGRAM_XML);
    await page.goto(seedModelerPath(GUARD_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  });

  test('palette has the locked bpmn-js set minus data store', async ({ page }) => {
    await expect(paletteEntry(page, 'space-tool')).toBeVisible();
    await expect(paletteEntry(page, 'create.intermediate-event')).toBeVisible();
    await expect(paletteEntry(page, 'create.subprocess-expanded')).toBeVisible();
    await expect(paletteEntry(page, 'create.participant-expanded')).toBeVisible();
    await expect(paletteEntry(page, 'create.group')).toBeVisible();
    await expect(paletteEntry(page, 'create.data-store')).toHaveCount(0);
  });

  test('Change element on a data object does not offer Data store', async ({ page }) => {
    const menu = await openChangeElementMenu(page, DATA_OBJECT_ID);
    await expect(menu.locator('[data-id="replace-with-data-store-reference"]')).toHaveCount(0);
    await expect(menu.getByText('Data store', { exact: true })).toHaveCount(0);
  });

  test('Data Store properties group is not shown on a task', async ({ page }) => {
    await selectElement(page, 'Activity_1');
    await expect(
      page.locator('.bio-properties-panel-group[data-group-id="group-custom-datastore-properties"]'),
    ).toHaveCount(0);
  });
});

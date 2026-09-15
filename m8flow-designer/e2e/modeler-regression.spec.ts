import { expect, test } from '@playwright/test';

import { editorCredentials, signInAsSharedRealmUser } from './helpers/auth';
import { openPropertiesPanelGroup, selectElement } from './helpers/diagram';
import {
  SEED_MODELER_PATH,
  SEED_USER_TASK_ELEMENT_ID,
  SEED_USER_TASK_NAME,
  seedModelerPath,
} from './helpers/fixtures';
import { seedProcessModelFile } from './helpers/seedFixture';

/**
 * CHK-11.. — Phase 0 baseline (see the phased Task Configuration Parity
 * plan). Locks in BpmnCanvas's current "Launch Editor" behavior *before*
 * later phases add more `spiff.*.requested`/`.edit` listeners next to it —
 * these two editors (Instructions/markdown, Pre-Script) are the only ones
 * BpmnCanvas answers today, and every later phase's spec file assumes this
 * one keeps passing. None of these tests click the top-level Save button —
 * they only exercise in-memory business-object edits, so the shared seed
 * fixture (wfh-approval.bpmn, also used by CHK-06..09) is left untouched.
 */
test.describe('m8flow-designer Process Modeler — properties panel regression baseline', () => {
  test('CHK-11: Instructions "Launch Editor" opens, edits, and commits markdown', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto(SEED_MODELER_PATH);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    const instructionsGroup = await openPropertiesPanelGroup(page, 'instructions');

    await instructionsGroup.getByRole('button', { name: 'Launch Editor' }).click();

    const dialog = page.getByRole('dialog', { name: 'Edit Instructions' });
    await expect(dialog).toBeVisible();

    // Monaco's editable surface is a hidden textarea, not a role="textbox" —
    // click into it and drive it via keyboard, the documented Playwright +
    // Monaco pattern, rather than a role locator that Monaco doesn't expose.
    const marker = `e2e-instructions-${Date.now()}`;
    await dialog.locator('.monaco-editor').click();
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
    await page.keyboard.type(marker);
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(dialog).toHaveCount(0);

    // Commit round-tripped back into the business object, not just closed —
    // the group's own Instructions textarea (the only <textarea> in this
    // group; its sibling entry is the Launch Editor button) now shows the
    // edited value.
    await expect(instructionsGroup.locator('textarea')).toHaveValue(marker);

    // Editing goes dirty (Save button appears) even though nothing was
    // persisted — confirms the edit really reached the command stack.
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
  });

  test('CHK-12: Pre-Script "Launch Editor" opens with a scriptType-specific title', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto(SEED_MODELER_PATH);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    const scriptsGroup = await openPropertiesPanelGroup(page, 'spiff_pre_post_scripts');

    // Pre-Script's button precedes Post-Script's in DOM order (scriptGroup()
    // renders Pre-Script's text area + button, then Post-Script's) — both
    // share the accessible name "Launch Editor", so position (not name)
    // disambiguates which one this targets.
    await scriptsGroup.getByRole('button', { name: 'Launch Editor' }).first().click();

    const dialog = page.getByRole('dialog', { name: `Edit Pre-Script — ${SEED_USER_TASK_NAME}` });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toHaveCount(0);
  });

  test('CHK-13: zoom controls and the properties-panel toggle still work', async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto(SEED_MODELER_PATH);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    await page.getByTitle('Zoom in').click();
    await page.getByTitle('Zoom out').click();
    await page.getByTitle('Fit to viewport').click();

    await page.getByTitle('Hide properties panel').click();
    await expect(page.getByTitle('Show properties panel')).toBeVisible();
    await page.getByTitle('Show properties panel').click();
    await expect(page.getByTitle('Hide properties panel')).toBeVisible();
  });

  test('Guest options are on a user task and checking them dirties the diagram', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto(SEED_MODELER_PATH);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    const guestGroup = await openPropertiesPanelGroup(page, 'allow_guest_user');
    await guestGroup.getByLabel('Guest can complete this task').check();
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
  });
});

const SCRIPT_FILE = 'checklist-script-task.bpmn';
const SCRIPT_TASK_ID = 'Activity_script';

const SCRIPT_DIAGRAM_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                   id="Definitions_script" targetNamespace="http://m8flow.org/e2e/script">
  <bpmn:process id="Process_script" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:scriptTask id="${SCRIPT_TASK_ID}" name="Compute" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="${SCRIPT_TASK_ID}" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="${SCRIPT_TASK_ID}" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_script">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="150" y="150" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_script_di" bpmnElement="${SCRIPT_TASK_ID}">
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

test.describe('m8flow-designer Process Modeler — script unit tests', () => {
  test.beforeEach(async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await seedProcessModelFile(page, SCRIPT_FILE, SCRIPT_DIAGRAM_XML);
    await page.goto(seedModelerPath(SCRIPT_FILE));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, SCRIPT_TASK_ID);
  });

  test('script-task Launch Editor Unit tests tab can create a case and run it', async ({
    page,
  }) => {
    const group = await openPropertiesPanelGroup(page, 'spiff_script');
    await group.getByRole('button', { name: 'Launch Editor' }).click();

    const dialog = page.getByRole('dialog', { name: 'Edit Script — Compute' });
    await expect(dialog).toBeVisible();
    await dialog.locator('.monaco-editor').click();
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
    await page.keyboard.type('x = 2');
    await dialog.getByRole('tab', { name: 'Unit tests' }).click();
    await dialog.getByRole('button', { name: 'Create unit test' }).click();
    await dialog.getByLabel('Expected output JSON').fill('{"x": 2}');
    await dialog.getByRole('button', { name: 'Run' }).click();
    await expect(dialog.getByRole('status')).toHaveText('Passed.');
  });
});


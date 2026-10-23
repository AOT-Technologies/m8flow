import { expect, test, type Locator } from '@playwright/test';

import { editorCredentials, useSession } from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import { SEED_PRIMARY_FILE } from './helpers/fixtures';
import { setModelStatus, setPrimaryFile, useActiveCatalog, type ActiveCatalogModel } from './helpers/mockCatalog';
import { fileRow, filesCount, logResult, menuItemLabels, mockApi, nameOfLength } from './helpers/processesPage';
import { deleteProcessModelFile, seedProcessModelFile } from './helpers/seedFixture';

/**
 * Process model page (opened from the Processes list).
 *
 * CHK-05        unknown model shows "Process model not found."
 * PRC-16..19    actions: Publish/Pause/Resume/Unpublish, Edit in modeler, Start process,
 *               Copy, Save as template.
 * PRC-20..23    sections: Instances, Files (add, upload, edit, download, delete), Tests.
 * PRC-33..34    page text, buttons and tooltips; empty model (mocked: no files, no instances).
 * PRC-35..39    form validation: Edit identity, Copy, Save as template, Add file,
 *               Create script unit test.
 * PRC-49..55    server errors (mocked 500), Set as primary, every file type, template
 *               visibility and tags, empty-name fallbacks, script unit test run,
 *               a real BPMN test file.
 *
 * A mock group with models (one with a running instance) and their files is
 * created before the tests; it and everything the tests create (copies,
 * templates, instances, files) is deleted afterwards.
 */

const stamp = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
const active = {
  groupId: `e2e-pm-${stamp}`,
  groupName: `E2E Process Model ${stamp}`,
  models: {
    live: { id: `e2e-live-${stamp}`, name: `E2E Live ${stamp}`, status: 'published', files: true, instance: true },
    draft: { id: `e2e-draft-${stamp}`, name: `E2E Draft ${stamp}`, status: 'draft', files: true, instance: false },
    detail: { id: `e2e-detail-${stamp}`, name: `E2E Detail ${stamp}`, status: 'draft', files: true, instance: false },
    files: { id: `e2e-files-${stamp}`, name: `E2E Files ${stamp}`, status: 'draft', files: true, instance: false },
    ident: { id: `e2e-ident-${stamp}`, name: `E2E Identity ${stamp}`, status: 'draft', files: true, instance: false },
    prim: { id: `e2e-prim-${stamp}`, name: `E2E Primary ${stamp}`, status: 'draft', files: true, instance: false },
    kinds: { id: `e2e-kinds-${stamp}`, name: `E2E Kinds ${stamp}`, status: 'draft', files: true, instance: false },
    scripts: { id: `e2e-scripts-${stamp}`, name: `E2E Scripts ${stamp}`, status: 'draft', files: false, instance: false },
    bpmntest: { id: `e2e-bpmntest-${stamp}`, name: `E2E BPMN Test ${stamp}`, status: 'draft', files: true, instance: false },
  } satisfies Record<string, ActiveCatalogModel>,
};
const M = active.models;
const route = (m: { id: string }) => `${active.groupId}:${m.id}`;
const escapeRe = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const SCRIPT_TASK_ID = 'Activity_script';
const USER_TASK_ID = 'Activity_e2e_approve';
/** A small diagram: start -> user task -> end, with <incoming>/<outgoing> on every element. */
function userTaskDiagram(): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  id="Definitions_e2e_approval" targetNamespace="http://m8flow.org/e2e/approval">
  <bpmn:process id="Process_e2e_approval" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="${USER_TASK_ID}" name="Approve">
      <bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="EndEvent_1"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="${USER_TASK_ID}" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="${USER_TASK_ID}" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_e2e_approval">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1"><dc:Bounds x="150" y="150" width="36" height="36" /></bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Approve_di" bpmnElement="${USER_TASK_ID}"><dc:Bounds x="250" y="128" width="100" height="80" /></bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1"><dc:Bounds x="420" y="150" width="36" height="36" /></bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;
}
/** A small diagram: start -> script task (running `script`) -> end. */
function scriptDiagram(script: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  id="Definitions_e2e_script" targetNamespace="http://m8flow.org/e2e/script">
  <bpmn:process id="Process_e2e_script" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:scriptTask id="${SCRIPT_TASK_ID}" name="Compute" scriptFormat="python">
      <bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing>
      <bpmn:script>${script}</bpmn:script>
    </bpmn:scriptTask>
    <bpmn:endEvent id="EndEvent_1"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="${SCRIPT_TASK_ID}" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="${SCRIPT_TASK_ID}" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_e2e_script">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1"><dc:Bounds x="150" y="150" width="36" height="36" /></bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Activity_script_di" bpmnElement="${SCRIPT_TASK_ID}"><dc:Bounds x="250" y="128" width="100" height="80" /></bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1"><dc:Bounds x="420" y="150" width="36" height="36" /></bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;
}

test.describe('Process model page', () => {
  test('CHK-05: Opening a process that does not exist shows "Process model not found."', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());

    await page.goto('/processes/does-not-exist:nope');

    await expect(page.getByText('Process model not found.', { exact: true })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    console.log('[CHK-05] Unknown process model shows "Process model not found."');
  });
});

test.describe('Process model page for a tenant with data', () => {
  const created = useActiveCatalog(test, { id: active.groupId, name: active.groupName }, Object.values(M));

  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
  });

  // ---------------- Actions on the process model page ----------------

  test('PRC-16: Publish, Pause, Resume and Unpublish from the process model page', async ({ page }) => {
    await setModelStatus(page, route(M.detail), 'draft');
    await page.goto(`/processes/${route(M.detail)}`);
    const status = page.getByTestId('process-model-status');
    const headerMenu = async () => {
      await page.getByRole('button', { name: 'More actions', exact: true }).click();
      return page.getByRole('menu');
    };

    await expect(status).toContainText('Draft');
    await expect(page.getByRole('link', { name: 'Open in modeler' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start process' })).toHaveCount(0);
    let menu = await headerMenu();
    expect(await menuItemLabels(menu)).toEqual(['Edit identity', 'Copy', 'Save as template']);
    await page.keyboard.press('Escape');

    await page.getByRole('button', { name: 'Publish', exact: true }).click();
    await expect(status).toContainText('Published');
    await expect(status).toContainText('Live. New instances can be started.');
    await expect(page.getByRole('link', { name: 'Edit in modeler' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start process' })).toBeVisible();

    menu = await headerMenu();
    expect(await menuItemLabels(menu)).toEqual(['Edit identity', 'Pause', 'Unpublish', 'Copy', 'Save as template']);
    await menu.getByRole('menuitem', { name: 'Pause', exact: true }).click();
    await expect(status).toContainText('Paused. Resume it to start new instances.');
    await expect(page.getByRole('button', { name: 'Start process' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Resume', exact: true }).click();
    await expect(status).toContainText('Published');

    menu = await headerMenu();
    await menu.getByRole('menuitem', { name: 'Unpublish', exact: true }).click();
    await expect(status).toContainText('Not published yet. Publish it to start instances.');
    await expect(page.getByRole('button', { name: 'Publish', exact: true })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);

    logResult('PRC-16', {
      scenario: 'Change the status from the process model page',
      actions: ['Publish', 'Menu -> Pause', 'Resume', 'Menu -> Unpublish'],
      expected: 'Status pill, hint, buttons and menu follow each change',
      actual: 'Draft -> Published -> Paused -> Published -> Draft; Start only when Published; menu matched each status',
      messages: [
        'Not published yet. Publish it to start instances.',
        'Live. New instances can be started.',
        'Paused. Resume it to start new instances.',
      ],
    });
  });

  test('PRC-17: "Edit in modeler" opens the main diagram and "Start process" starts an instance', async ({
    page,
  }) => {
    await setModelStatus(page, route(M.detail), 'published');
    await page.goto(`/processes/${route(M.detail)}`);
    await page.getByRole('link', { name: 'Edit in modeler' }).click();
    await expect(page).toHaveURL(new RegExp(`/processes/${route(M.detail)}/modeler/${SEED_PRIMARY_FILE}`));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    await page.goto(`/processes/${route(M.detail)}`);
    await page.getByRole('button', { name: 'Start process' }).click();
    await expect(page).toHaveURL(/\/process-instances\/\d+/);
    const instanceId = Number(/process-instances\/(\d+)/.exec(page.url())?.[1]);
    created.instances.push(instanceId);

    await page.goto(`/processes/${route(M.detail)}`);
    await expect(page.locator('#instances').getByRole('link', { name: String(instanceId), exact: true })).toBeVisible();

    logResult('PRC-17', {
      scenario: 'Edit and run a published model from its page',
      actions: ['Click "Edit in modeler"', 'Click "Start process"'],
      expected: 'Modeler opens the primary diagram; Start opens the new instance, which is listed under Recent instances',
      actual: `Modeler opened ${SEED_PRIMARY_FILE}; instance ${instanceId} started and listed`,
    });
  });

  test('PRC-18: Copy creates a duplicate with the same files; a used id is refused', async ({ page }) => {
    const copyId = `${M.detail.id}-copy`;
    const copyName = `${M.detail.name} (copy)`;
    created.models.push(`${active.groupId}:${copyId}`);

    await page.goto(`/processes/${route(M.detail)}`);
    const originalFiles = await filesCount(page);
    const openCopy = async () => {
      await page.getByRole('button', { name: 'More actions', exact: true }).click();
      await page.getByRole('menuitem', { name: 'Copy', exact: true }).click();
      return page.getByRole('dialog', { name: 'Copy process model' });
    };

    let dialog = await openCopy();
    const intro = 'Creates a duplicate in the same process group. Files are copied; process instances are not.';
    await expect(dialog.getByText(intro)).toBeVisible();
    await expect(dialog.getByLabel('Process model ID')).toHaveValue(copyId);
    await expect(dialog.getByLabel('Display name')).toHaveValue(copyName);
    const submit = dialog.getByRole('button', { name: 'Copy process model' });
    await dialog.getByLabel('Process model ID').fill('');
    await expect(submit).toBeDisabled();
    await dialog.getByLabel('Process model ID').fill(copyId);
    await submit.click();

    await expect(page).toHaveURL(new RegExp(`/processes/${active.groupId}:${copyId}$`));
    await expect(page.getByRole('heading', { name: copyName, exact: true })).toBeVisible();
    expect(await filesCount(page)).toBe(originalFiles);
    await expect(page.locator('#instances').getByText('No instances yet.')).toBeVisible();

    await page.goto(`/processes/${route(M.detail)}`);
    dialog = await openCopy();
    await dialog.getByRole('button', { name: 'Copy process model' }).click();
    const error = dialog.getByRole('alert');
    await expect(error).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/processes/${route(M.detail)}$`));
    const errorText = await error.innerText();
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();

    logResult('PRC-18', {
      scenario: 'Copy a process model',
      actions: ['Menu -> Copy', 'Clear id (button disabled)', 'Copy', 'Copy again with the same id'],
      expected: 'Copy opens with the same files and no instances; a second copy with the same id is refused',
      actual: `"${copyName}" created with ${originalFiles} files; second copy refused`,
      messages: [intro, errorText],
    });
  });

  test('PRC-19: Save as template checks the name and creates a template', async ({ page }) => {
    const templateName = `E2E Template ${stamp}`;
    await page.goto(`/processes/${route(M.detail)}`);
    await page.getByRole('button', { name: 'More actions', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Save as template', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: 'Save as template' });
    const nameInput = dialog.getByLabel('Name', { exact: true });
    await expect(nameInput).toHaveValue(M.detail.name);
    await expect(dialog.getByRole('combobox', { name: 'Visibility' })).toContainText('Private');
    const submit = dialog.getByRole('button', { name: 'Create template' });

    await nameInput.fill('');
    await expect(submit).toBeDisabled();
    await nameInput.fill('Bad@Name!');
    await submit.click();
    const invalid = 'Name may only contain letters, numbers, spaces, hyphens and underscores.';
    await expect(dialog.getByRole('alert')).toHaveText(invalid);

    await nameInput.fill(templateName);
    await dialog.getByLabel('Description (optional)').fill('E2E mock data -- safe to delete');
    await dialog.getByLabel('Category (optional)').fill('E2E');
    await dialog.getByLabel('Tags (comma-separated, optional)').fill('e2e, mock');
    await submit.click();

    await expect(page).toHaveURL(/\/templates\/\d+/);
    const templateId = Number(/templates\/(\d+)/.exec(page.url())?.[1]);
    created.templates.push(templateId);
    const saved = await backendFetch(page, `/v1.0/m8flow/templates/${templateId}`);
    expect(saved.status).toBe(200);
    expect((saved.body as { name: string }).name).toBe(templateName);

    logResult('PRC-19', {
      scenario: 'Save a process model as a template',
      actions: ['Menu -> Save as template', 'Empty name', 'Invalid name', `Name "${templateName}"`, 'Create template'],
      expected: 'Empty name disables Create; invalid characters are refused; a valid name creates the template and opens it',
      actual: `Template ${templateId} "${templateName}" created and opened`,
      messages: [invalid],
    });
  });

  // ---------------- Instances, files and tests ----------------

  test('PRC-20: The Instances section lists recent instances, and shows a message when there are none', async ({
    page,
  }) => {
    const seeded = created.instances[0];
    await page.goto(`/processes/${route(M.live)}`);
    await expect(page.getByRole('link', { name: 'Instances', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: /^Files \(\d+\)$/ })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Tests', exact: true })).toBeVisible();

    await page.getByRole('link', { name: 'Instances', exact: true }).click();
    await expect(page).toHaveURL(/#instances$/);
    const section = page.locator('#instances');
    await expect(section.getByRole('heading', { name: 'Recent instances' })).toBeVisible();
    const link = section.getByRole('link', { name: String(seeded), exact: true });
    await expect(link).toHaveAttribute('href', `/process-instances/${seeded}`);
    const row = section.getByRole('row').filter({ has: page.getByRole('link', { name: String(seeded), exact: true }) });
    await expect(row).toContainText(editorCredentials().username);
    const viewAll = section.getByRole('link', { name: /^View all \d+$/ });
    await expect(viewAll).toHaveAttribute('href', `/process-instances?search=${encodeURIComponent(M.live.name)}`);
    const viewAllText = await viewAll.innerText();

    await page.goto(`/processes/${route(M.draft)}`);
    await expect(page.locator('#instances').getByText('No instances yet.')).toBeVisible();

    logResult('PRC-20', {
      scenario: 'Recent instances on a model with and without instances',
      actions: ['Open the model with an instance', 'Click "Instances"', 'Open a model with no instances'],
      expected: 'Instance listed with link and starter; "View all" opens the filtered instance list; empty message otherwise',
      actual: `Instance ${seeded} listed, started by ${editorCredentials().username}; "${viewAllText}" link correct; draft model shows the empty message`,
      messages: ['No instances yet.'],
    });
  });

  test('PRC-21: Files can be added as a new file or an upload; a used name or a missing upload is refused', async ({
    page,
  }) => {
    const uploadName = `e2e-upload-${stamp}.txt`;
    const notesName = `e2e-notes-${stamp}.md`;
    await page.goto(`/processes/${route(M.files)}`);
    const before = await filesCount(page);
    await page.getByRole('link', { name: /^Files \(\d+\)$/ }).click();
    await expect(page).toHaveURL(/#files$/);

    const openAdd = async () => {
      await page.getByRole('button', { name: 'Add file', exact: true }).click();
      return page.getByRole('dialog', { name: 'Add file' });
    };
    let dialog = await openAdd();
    const intro = 'BPMN, DMN, JSON, and Markdown open in the modeler.';
    await expect(dialog.getByText(intro)).toBeVisible();
    await expect(dialog.getByRole('combobox', { name: 'File type' })).toContainText('BPMN');
    const submit = dialog.getByRole('button', { name: 'Add file', exact: true });
    await expect(submit).toBeDisabled();

    // Name already used (".bpmn" is added automatically).
    await dialog.getByLabel('File name').fill(SEED_PRIMARY_FILE.replace(/\.bpmn$/, ''));
    await submit.click();
    const duplicate = 'A file with this name already exists.';
    await expect(dialog.getByRole('alert')).toHaveText(duplicate);

    // Upload without choosing a file, then with a file.
    await dialog.getByRole('combobox', { name: 'File type' }).click();
    await page.getByRole('option', { name: 'Upload', exact: true }).click();
    await dialog.getByLabel('File name').fill(uploadName);
    await submit.click();
    const noFile = 'Choose a file to upload.';
    await expect(dialog.getByRole('alert')).toHaveText(noFile);
    await dialog.getByLabel('Upload file').setInputFiles({
      name: uploadName,
      mimeType: 'text/plain',
      buffer: Buffer.from('E2E upload -- safe to delete'),
    });
    await submit.click();
    await expect(dialog).toHaveCount(0);
    await expect(fileRow(page, uploadName)).toContainText('TXT');
    expect(await filesCount(page)).toBe(before + 1);

    // New Markdown file opens in the modeler.
    dialog = await openAdd();
    await dialog.getByRole('combobox', { name: 'File type' }).click();
    await page.getByRole('option', { name: 'Markdown', exact: true }).click();
    await dialog.getByLabel('File name').fill(notesName.replace(/\.md$/, ''));
    await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/modeler/${notesName}$`));

    await page.goto(`/processes/${route(M.files)}`);
    await expect(fileRow(page, notesName)).toContainText('Markdown');
    expect(await filesCount(page)).toBe(before + 2);

    logResult('PRC-21', {
      scenario: 'Add files to a process model',
      actions: ['Add file with a used name', 'Upload with no file', `Upload ${uploadName}`, `New Markdown ${notesName}`],
      expected: 'Used name and missing upload refused; upload listed on the page; Markdown opens in the modeler',
      actual: `Files ${before} -> ${before + 2}; ${uploadName} listed as TXT; ${notesName} opened in the modeler`,
      messages: [intro, duplicate, noFile],
    });
  });

  test('PRC-22: Files can be edited, downloaded and deleted; the primary file cannot be deleted', async ({
    page,
  }) => {
    const removable = `e2e-remove-${stamp}.txt`;
    const schema = 'wfh-form-schema.json';
    await seedProcessModelFile(page, removable, 'E2E file -- safe to delete', route(M.files));
    await page.goto(`/processes/${route(M.files)}`);
    const before = await filesCount(page);

    const primary = fileRow(page, SEED_PRIMARY_FILE);
    await expect(primary.getByText('Primary', { exact: true })).toBeVisible();
    await expect(primary.getByRole('button', { name: 'Delete file' })).toHaveCount(0);

    await fileRow(page, schema).getByRole('link', { name: 'Edit file' }).click();
    await expect(page).toHaveURL(new RegExp(`/modeler/${schema}$`));
    await page.goto(`/processes/${route(M.files)}`);

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      fileRow(page, schema).getByRole('button', { name: 'Download file' }).click(),
    ]);
    expect(download.suggestedFilename()).toBe(schema);
    const chunks: Buffer[] = [];
    for await (const chunk of await download.createReadStream()) chunks.push(chunk as Buffer);
    expect(Buffer.concat(chunks).toString('utf-8')).toContain('Work From Home Request');

    const confirm = page.getByRole('alertdialog', { name: 'Delete file' });
    const question = `Delete ${removable}? This cannot be undone.`;
    await fileRow(page, removable).getByRole('button', { name: 'Delete file' }).click();
    await expect(confirm).toContainText(question);
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(fileRow(page, removable)).toBeVisible();
    await fileRow(page, removable).getByRole('button', { name: 'Delete file' }).click();
    await confirm.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(confirm).toHaveCount(0);
    await expect(page.getByRole('link', { name: removable, exact: true })).toHaveCount(0);
    expect(await filesCount(page)).toBe(before - 1);

    logResult('PRC-22', {
      scenario: 'Manage existing files',
      actions: ['Check primary file', `Edit ${schema}`, `Download ${schema}`, `Delete ${removable} (Cancel, then Delete)`],
      expected: 'Primary has no Delete; Edit opens the modeler; download has the file content; Delete asks first and removes the file',
      actual: `Edit and download of ${schema} worked; ${removable} kept on Cancel and removed on Delete (files ${before} -> ${before - 1})`,
      messages: [question],
    });
  });

  test('PRC-23: The Tests section runs BPMN tests and checks script unit test input', async ({ page }) => {
    const testFile = `test_e2e-${stamp}.json`;
    try {
      await page.goto(`/processes/${route(M.files)}`);
      await page.getByRole('link', { name: 'Tests', exact: true }).click();
      await expect(page).toHaveURL(/#tests$/);
      const card = page.locator('#tests');
      await expect(card.getByText('BPMN unit tests (test_*.json) and script-task unit tests')).toBeVisible();
      await expect(card.getByRole('button', { name: 'Run BPMN tests' })).toBeDisabled();
      await expect(card.getByText('No script unit tests yet.')).toBeVisible();

      await card.getByRole('button', { name: 'Create script unit test' }).click();
      const create = page.getByRole('dialog', { name: 'Create script unit test' });
      const createBtn = create.getByRole('button', { name: 'Create', exact: true });
      await expect(createBtn).toBeDisabled();
      await create.getByLabel('Script task ID').fill('Script_1');
      await create.getByLabel('Input JSON').fill('{bad');
      await createBtn.click();
      const badJson = 'Input JSON must be valid JSON';
      await expect(create.getByRole('alert')).toHaveText(badJson);
      await create.getByRole('button', { name: 'Cancel', exact: true }).click();

      // With a test_*.json file the Run button is enabled; results are mocked.
      await seedProcessModelFile(page, testFile, '{}', route(M.files));
      const runPath = /\/v1\.0\/m8flow\/process-models\/[^/]+\/tests\/run$/;
      await mockApi(page, { method: 'POST', path: runPath }, 200, {
        all_passed: true,
        passing: [{ bpmn_file: SEED_PRIMARY_FILE, test_case_identifier: 'e2e_case' }],
        failing: [],
      });
      await page.reload();
      await card.getByRole('button', { name: 'Run BPMN tests' }).click();
      const results = page.getByRole('dialog', { name: 'BPMN test results' });
      await expect(results).toContainText('All 1 test passed.');
      await results.getByRole('button', { name: 'Close', exact: true }).last().click();

      await mockApi(page, { method: 'POST', path: runPath }, 200, {
        all_passed: false,
        passing: [],
        failing: [
          {
            bpmn_file: SEED_PRIMARY_FILE,
            test_case_identifier: 'e2e_case',
            test_case_error_details: { error_messages: ['Expected x to be 2'] },
          },
        ],
      });
      await card.getByRole('button', { name: 'Run BPMN tests' }).click();
      await expect(results).toContainText('1 failed, 0 passed.');
      await expect(results).toContainText('e2e_case — Expected x to be 2');
      await results.getByRole('button', { name: 'Close', exact: true }).last().click();

      logResult('PRC-23', {
        scenario: 'Tests section without and with a BPMN test file (results mocked)',
        actions: ['Open Tests', 'Create script unit test with bad JSON', `Add ${testFile}`, 'Run BPMN tests (pass)', 'Run BPMN tests (fail)'],
        expected: 'Run disabled without test files; bad JSON refused; pass and fail results shown',
        actual: 'Run disabled, then enabled after adding the test file; bad JSON refused; pass and fail summaries shown',
        messages: ['No script unit tests yet.', badJson, 'All 1 test passed.', '1 failed, 0 passed.'],
      });
    } finally {
      await deleteProcessModelFile(page, testFile, route(M.files));
    }
  });

  // ---------------- Page text and empty states ----------------

  test('PRC-33: The process model page shows its labels, sections, buttons and tooltips', async ({ page }) => {
    await page.goto(`/processes/${route(M.live)}`);
    await expect(page.getByRole('button', { name: 'All processes' })).toBeEnabled();
    await expect(page.getByRole('heading', { name: M.live.name, exact: true })).toBeVisible();
    const status = page.getByTestId('process-model-status');
    await expect(status).toContainText('Published');
    await expect(status).toContainText('Live. New instances can be started.');
    const groupLink = page.getByRole('link', { name: active.groupName, exact: true }).first();
    await expect(groupLink).toHaveAttribute('href', `/processes?group=${encodeURIComponent(active.groupId)}`);
    for (const label of ['Last run', 'Running now', 'Runs 30d', 'Median time', 'Errors 30d', 'Group', 'Identifier']) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByText(`${active.groupId}/${M.live.id}`, { exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Edit in modeler' })).toHaveAttribute(
      'href',
      `/processes/${route(M.live)}/modeler/${SEED_PRIMARY_FILE}`,
    );
    await expect(page.getByRole('button', { name: 'Start process' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'More actions', exact: true })).toBeEnabled();

    const instances = page.locator('#instances');
    await expect(instances.getByRole('heading', { name: 'Recent instances' })).toBeVisible();
    for (const header of ['ID', 'Started by', 'Start', 'Duration', 'Status']) {
      await expect(instances.getByRole('columnheader', { name: header, exact: true })).toBeVisible();
    }

    const files = page.locator('#files');
    await expect(files.getByRole('heading', { name: 'Files', exact: true })).toBeVisible();
    await expect(files.getByText('BPMN, form schema and UI schema')).toBeVisible();
    await expect(files.getByRole('button', { name: 'Add file' })).toBeEnabled();
    // Tooltips (title) on the file buttons.
    const primary = fileRow(page, SEED_PRIMARY_FILE);
    await expect(primary.getByRole('link', { name: SEED_PRIMARY_FILE, exact: true })).toHaveAttribute('title', `Edit ${SEED_PRIMARY_FILE}`);
    await expect(primary.getByRole('link', { name: 'Edit file' })).toHaveAttribute('title', 'Edit file');
    await expect(primary.getByRole('button', { name: 'Download file' })).toHaveAttribute('title', 'Download file');
    await expect(primary.getByRole('button', { name: 'Delete file' })).toHaveCount(0);
    await expect(primary.getByRole('button', { name: 'Set as primary' })).toHaveCount(0);
    const schema = fileRow(page, 'wfh-form-schema.json');
    await expect(schema).toContainText('Form schema');
    await expect(schema.getByRole('button', { name: 'Delete file' })).toHaveAttribute('title', 'Delete file');
    await expect(fileRow(page, 'wfh-form-uischema.json')).toContainText('UI schema');

    const tests = page.locator('#tests');
    await expect(tests.getByRole('heading', { name: 'Tests', exact: true })).toBeVisible();
    await expect(tests.getByRole('heading', { name: 'Script unit tests' })).toBeVisible();
    await expect(tests.getByRole('button', { name: 'Create script unit test' })).toBeEnabled();

    await page.getByRole('button', { name: 'All processes' }).click();
    await expect(page).toHaveURL(/\/processes$/);

    logResult('PRC-33', {
      scenario: 'Labels and controls of a published process model page',
      actions: ['Open the model page', 'Check header, numbers, facts, sections, file tooltips', 'Click "All processes"'],
      expected: 'All labels, sections and enabled buttons shown; file buttons have tooltips; primary file has no Delete; "All processes" goes back',
      actual: 'All labels, column headers and tooltips matched; primary file has no Delete or Set as primary; back to Processes',
      messages: ['Live. New instances can be started.', 'BPMN, form schema and UI schema'],
    });
  });

  test('PRC-34: A brand-new process model with no files or instances shows empty messages (mocked API)', async ({
    page,
  }) => {
    const detailPath = `/v1.0/m8flow/process-models/${route(M.draft)}`;
    const real = (await backendFetch(page, detailPath)).body as Record<string, unknown>;
    await mockApi(page, { method: 'GET', path: detailPath }, 200, {
      ...real,
      files: [],
      recent_instances: [],
      runs_30d: 0,
      running_now: 0,
      last_run_at: null,
    });
    await page.goto(`/processes/${route(M.draft)}`);

    await expect(page.getByRole('link', { name: 'Files (0)' })).toBeVisible();
    await expect(page.locator('#files').getByText('No files yet.')).toBeVisible();
    await expect(page.locator('#instances').getByText('No instances yet.')).toBeVisible();
    await expect(page.locator('#instances').getByRole('link', { name: 'View all 0' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open in modeler' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Publish', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Start process' })).toHaveCount(0);
    await expect(page.locator('#tests').getByRole('button', { name: 'Run BPMN tests' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Add file' })).toBeEnabled();

    logResult('PRC-34', {
      scenario: 'New model with no files and no instances (detail call mocked)',
      actions: ['Open the model page'],
      expected: 'Files (0) and "No files yet."; "No instances yet."; Open in modeler and Run BPMN tests disabled; Add file and Publish available',
      actual: 'Empty messages shown; Open in modeler and Run BPMN tests disabled; Add file and Publish enabled; no Start',
      messages: ['No files yet.', 'No instances yet.'],
    });
  });

  // ---------------- Form validation on the process model page ----------------

  test('PRC-35: Edit identity shows the current values, Cancel keeps them and Save trims the new values', async ({
    page,
  }) => {
    const renamed = `E2E Renamed #1 & Co ${stamp}`;
    await page.goto(`/processes/${route(M.ident)}`);
    const openEdit = async () => {
      await page.getByRole('button', { name: 'More actions', exact: true }).click();
      await page.getByRole('menuitem', { name: 'Edit identity', exact: true }).click();
      return page.getByRole('dialog', { name: 'Edit process model' });
    };

    let dialog = await openEdit();
    const intro = 'Display name and description only. The identifier does not change.';
    await expect(dialog.getByText(intro)).toBeVisible();
    await expect(dialog.getByLabel('Process model display name')).toHaveValue(M.ident.name);
    await expect(dialog.getByLabel('Process model description')).toHaveValue('E2E mock data -- safe to delete');
    await expect(dialog.getByRole('button', { name: 'Save', exact: true })).toBeEnabled();
    await dialog.getByLabel('Process model display name').fill('Not saved');
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByRole('heading', { name: M.ident.name, exact: true })).toBeVisible();

    dialog = await openEdit();
    await dialog.getByLabel('Process model display name').fill(`   ${renamed}   `);
    await dialog.getByLabel('Process model description').fill('   Updated by E2E   ');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole('heading', { name: renamed, exact: true })).toBeVisible();
    await expect(page.getByText('Updated by E2E', { exact: true })).toBeVisible();
    await expect(page.getByText(`${active.groupId}/${M.ident.id}`, { exact: true })).toBeVisible();
    const saved = (await backendFetch(page, `/v1.0/m8flow/process-models/${route(M.ident)}`)).body as {
      display_name: string;
      description: string;
    };
    expect(saved.display_name).toBe(renamed);
    expect(saved.description).toBe('Updated by E2E');

    logResult('PRC-35', {
      scenario: 'Edit the name and description of a process model',
      actions: ['Menu -> Edit identity -> Cancel', 'Menu -> Edit identity -> name and description with spaces -> Save'],
      expected: 'Form shows current values; Cancel keeps them; Save stores trimmed values; identifier unchanged',
      actual: `Renamed to "${renamed}"; description "Updated by E2E"; identifier unchanged`,
      messages: [intro],
    });
  });

  test('PRC-36: Copy refuses empty and invalid ids and trims spaces around a valid id', async ({ page }) => {
    const leaf = `${M.draft.id}-trim-copy`;
    created.models.push(`${active.groupId}:${leaf}`);
    await page.goto(`/processes/${route(M.draft)}`);
    await page.getByRole('button', { name: 'More actions', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Copy', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Copy process model' });
    const id = dialog.getByLabel('Process model ID');
    const name = dialog.getByLabel('Display name');
    const submit = dialog.getByRole('button', { name: 'Copy process model' });
    await expect(id).toHaveAttribute('placeholder', 'invoice-approval-copy');
    await expect(name).toHaveAttribute('placeholder', 'Invoice Approval (copy)');
    await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled();
    const checks: string[] = [];

    await id.fill('   ');
    await expect(submit).toBeDisabled();
    checks.push('space-only id: Copy disabled');
    for (const bad of ['Bad Id!', 'a/b']) {
      await id.fill(bad);
      await submit.click();
      await expect(dialog.getByRole('alert')).toContainText('failed: 400');
      checks.push(`id "${bad}": refused`);
    }
    const message = await dialog.getByRole('alert').innerText();

    await id.fill(`  ${leaf}  `);
    await name.fill(`  E2E Trimmed Copy ${stamp}  `);
    await submit.click();
    await expect(page).toHaveURL(new RegExp(`/processes/${active.groupId}:${leaf}$`));
    await expect(page.getByRole('heading', { name: `E2E Trimmed Copy ${stamp}`, exact: true })).toBeVisible();
    checks.push(`id with spaces: copy created as "${leaf}"`);

    logResult('PRC-36', {
      scenario: 'Copy dialog with empty, invalid and space-padded values',
      actions: ['Space-only id', 'Invalid ids', 'Valid id and name with spaces'],
      expected: 'Copy disabled for a space-only id; invalid ids refused; spaces around a valid id and name are removed',
      actual: checks.join('; '),
      messages: [message],
    });
  });

  test('PRC-37: Save as template enforces the name rules, the 100-character limit and unique names', async ({
    page,
  }) => {
    const longName = nameOfLength(`E2E Template Max ${stamp} `, 100);
    const openDialog = async () => {
      await page.goto(`/processes/${route(M.draft)}`);
      await page.getByRole('button', { name: 'More actions', exact: true }).click();
      await page.getByRole('menuitem', { name: 'Save as template', exact: true }).click();
      return page.getByRole('dialog', { name: 'Save as template' });
    };
    let dialog = await openDialog();
    const intro = "Creates a draft template from this process model's BPMN, DMN, form-schema, and markdown files.";
    await expect(dialog.getByText(intro)).toBeVisible();
    for (const label of ['Name', 'Description (optional)', 'Category (optional)', 'Visibility', 'Tags (comma-separated, optional)']) {
      await expect(dialog.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(dialog.getByLabel('Tags (comma-separated, optional)')).toHaveAttribute('placeholder', 'finance, approval');
    const name = dialog.getByLabel('Name', { exact: true });
    const submit = dialog.getByRole('button', { name: 'Create template' });
    const checks: string[] = [];

    await name.fill('     ');
    await expect(submit).toBeDisabled();
    checks.push('space-only name: Create disabled');
    const noLetter = 'Name must include a letter or number.';
    for (const value of ['___', '- - -']) {
      await name.fill(value);
      await submit.click();
      await expect(dialog.getByRole('alert')).toHaveText(noLetter);
      checks.push(`"${value}": refused`);
    }
    // Typing stops at 100 characters (the field's limit).
    await name.fill('');
    await name.pressSequentially('x'.repeat(130));
    await expect(name).toHaveValue('x'.repeat(100));
    checks.push('130 characters typed: field keeps 100');

    await name.fill(longName);
    await submit.click();
    await expect(page).toHaveURL(/\/templates\/\d+/);
    const templateId = Number(/templates\/(\d+)/.exec(page.url())?.[1]);
    created.templates.push(templateId);
    checks.push(`100-character name: template ${templateId} created`);

    dialog = await openDialog();
    await dialog.getByLabel('Name', { exact: true }).fill(longName);
    await dialog.getByRole('button', { name: 'Create template' }).click();
    const duplicate = `A template named '${longName}' already exists. Please choose a different name.`;
    await expect(dialog.getByRole('alert')).toHaveText(duplicate);
    await expect(page).toHaveURL(new RegExp(`/processes/${route(M.draft)}$`));
    checks.push('same name again: refused');

    logResult('PRC-37', {
      scenario: 'Save as template name rules',
      actions: ['Space-only name', 'Names without letters or numbers', '130 characters', '100-character name', 'Same name again'],
      expected: 'Space-only disables Create; names without a letter/number refused; field stops at 100; 100 characters accepted; duplicate refused',
      actual: checks.join('; '),
      messages: [intro, noLetter, 'A template named ... already exists. Please choose a different name.'],
    });
  });

  test('PRC-38: Add file trims names, adds the right extension and refuses invalid names and file types', async ({
    page,
  }) => {
    const trimmed = `e2e-trim-${stamp}`;
    const withSuffix = `e2e-suffix-${stamp}.bpmn`;
    await page.goto(`/processes/${route(M.files)}`);
    const openAdd = async () => {
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.getByRole('button', { name: 'Add file', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Add file' });
      await expect(dialog.getByLabel('File name')).toHaveValue('');
      return dialog;
    };
    const chooseType = async (dialog: Locator, type: string) => {
      await dialog.getByRole('combobox', { name: 'File type' }).click();
      await page.getByRole('option', { name: type, exact: true }).click();
    };
    const checks: string[] = [];

    let dialog = await openAdd();
    await dialog.getByRole('combobox', { name: 'File type' }).click();
    for (const type of ['BPMN', 'DMN', 'JSON', 'Markdown', 'Upload']) {
      await expect(page.getByRole('option', { name: type, exact: true })).toBeVisible();
    }
    await page.keyboard.press('Escape');
    const fileName = dialog.getByLabel('File name');
    await expect(fileName).toHaveAttribute('placeholder', 'diagram.bpmn');
    await chooseType(dialog, 'Markdown');
    await expect(fileName).toHaveAttribute('placeholder', 'diagram.md');
    await chooseType(dialog, 'Upload');
    await expect(fileName).toHaveAttribute('placeholder', 'notes.txt');
    await expect(dialog.getByLabel('Upload file')).toBeVisible();
    checks.push('types and placeholders matched');

    await chooseType(dialog, 'BPMN');
    await fileName.fill('     ');
    await expect(dialog.getByRole('button', { name: 'Add file', exact: true })).toBeDisabled();
    checks.push('space-only name: Add disabled');

    // Names and types the server refuses.
    const refused: [string, string][] = [
      ['BPMN', 'bad/name'],
      ['JSON', 'process_model'],
    ];
    for (const [type, value] of refused) {
      await chooseType(dialog, type);
      await fileName.fill(value);
      await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
      // A reserved name may already be known to the page ("already exists") or refused by the server.
      await expect(dialog.getByRole('alert')).toHaveText(/failed: 400|A file with this name already exists\./);
      checks.push(`${type} "${value}": refused (${await dialog.getByRole('alert').innerText()})`);
    }
    await chooseType(dialog, 'Upload');
    await fileName.fill('');
    await dialog.getByLabel('Upload file').setInputFiles({
      name: `e2e-bad-${stamp}.exe`,
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('not allowed'),
    });
    await expect(fileName).toHaveValue(`e2e-bad-${stamp}.exe`);
    await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('failed: 400');
    const message = await dialog.getByRole('alert').innerText();
    checks.push('.exe upload: refused');
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);

    // Spaces around the name are removed; an extension already typed is not added twice.
    dialog = await openAdd();
    await chooseType(dialog, 'Markdown');
    await dialog.getByLabel('File name').fill(`   ${trimmed}   `);
    await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/modeler/${trimmed}\\.md$`));
    checks.push(`"   ${trimmed}   " saved as ${trimmed}.md`);

    await page.goto(`/processes/${route(M.files)}`);
    dialog = await openAdd();
    await dialog.getByLabel('File name').fill(withSuffix);
    await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/modeler/${withSuffix.replace('.', '\\.')}$`));
    checks.push(`"${withSuffix}" saved without a second .bpmn`);

    logResult('PRC-38', {
      scenario: 'Add file names, types and extensions',
      actions: ['Check types and placeholders', 'Space-only name', 'Name with "/"', 'Reserved name', '.exe upload', 'Name with spaces', 'Name with extension'],
      expected: 'Space-only disables Add; invalid name, reserved name and .exe refused; spaces removed; extension not doubled',
      actual: checks.join('; '),
      messages: [message],
    });
  });

  test('PRC-39: Create script unit test refuses an empty task id and input that is not a JSON object', async ({
    page,
  }) => {
    await page.goto(`/processes/${route(M.files)}`);
    await page.locator('#tests').getByRole('button', { name: 'Create script unit test' }).click();
    const dialog = page.getByRole('dialog', { name: 'Create script unit test' });
    const task = dialog.getByLabel('Script task ID');
    const input = dialog.getByLabel('Input JSON');
    const expected = dialog.getByLabel('Expected output JSON');
    const create = dialog.getByRole('button', { name: 'Create', exact: true });
    await expect(task).toHaveAttribute('placeholder', 'Script_1');
    await expect(input).toHaveValue('{}');
    await expect(expected).toHaveValue('{}');
    await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled();
    const checks: string[] = [];

    await task.fill('     ');
    await expect(create).toBeDisabled();
    checks.push('space-only task id: Create disabled');

    await task.fill('Script_1');
    const cases: [Locator, string, string][] = [
      [input, '[1, 2]', 'Input JSON must be a JSON object'],
      [input, 'null', 'Input JSON must be a JSON object'],
      [input, '"text"', 'Input JSON must be a JSON object'],
      [expected, '{bad', 'Expected output JSON must be valid JSON'],
      [expected, '42', 'Expected output JSON must be a JSON object'],
    ];
    for (const [field, value, message] of cases) {
      await input.fill('{}');
      await expected.fill('{}');
      await field.fill(value);
      await create.click();
      await expect(dialog.getByRole('alert')).toHaveText(message);
      checks.push(`${value}: "${message}"`);
    }
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator('#tests').getByText('No script unit tests yet.')).toBeVisible();

    logResult('PRC-39', {
      scenario: 'Create script unit test with missing or invalid values',
      actions: ['Space-only task id', 'Input: array, null, text', 'Expected output: invalid JSON, number'],
      expected: 'Create disabled without a task id; each invalid value refused with its own message; nothing created',
      actual: checks.join('; '),
      messages: [...new Set(cases.map((c) => c[2]))],
    });
  });

  // ---------------- More edge cases ----------------

  test('PRC-49: Server errors on the process model page are shown and nothing changes', async ({ page }) => {
    const reason = 'Service unavailable';
    const model = `/v1\\.0/m8flow/process-models/${escapeRe(route(M.draft))}`;
    await mockApi(page, { method: 'POST', path: new RegExp(`^${model}/copy$`) }, 500, {});
    await mockApi(page, { method: 'POST', path: '/v1.0/m8flow/templates' }, 500, { message: reason });
    await mockApi(page, { method: 'POST', path: new RegExp(`^${model}/files$`) }, 500, {});
    await mockApi(page, { method: 'DELETE', path: new RegExp(`^${model}/files/.+$`) }, 500, {});
    await mockApi(page, { method: 'PUT', path: new RegExp(`^${model}$`) }, 500, {});
    const menuAction = async (item: string, title: string) => {
      await page.getByRole('button', { name: 'More actions', exact: true }).click();
      await page.getByRole('menuitem', { name: item, exact: true }).click();
      return page.getByRole('dialog', { name: title });
    };
    const checks: string[] = [];

    await page.goto(`/processes/${route(M.draft)}`);
    let dialog = await menuAction('Copy', 'Copy process model');
    await dialog.getByRole('button', { name: 'Copy process model' }).click();
    await expect(dialog.getByRole('alert')).toContainText('failed: 500');
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    checks.push('Copy');

    dialog = await menuAction('Save as template', 'Save as template');
    await dialog.getByLabel('Name', { exact: true }).fill(`E2E Fail Template ${stamp}`);
    await dialog.getByRole('button', { name: 'Create template' }).click();
    await expect(dialog.getByRole('alert')).toHaveText(reason);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    checks.push('Save as template');

    dialog = await menuAction('Edit identity', 'Edit process model');
    await dialog.getByLabel('Process model display name').fill('Not saved');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('failed: 500');
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByRole('heading', { name: M.draft.name, exact: true })).toBeVisible();
    checks.push('Edit identity');

    await page.getByRole('button', { name: 'Add file', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Add file' });
    await dialog.getByLabel('File name').fill(`e2e-fail-${stamp}`);
    await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('failed: 500');
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    checks.push('Add file');

    await fileRow(page, 'wfh-form-schema.json').getByRole('button', { name: 'Delete file' }).click();
    const confirm = page.getByRole('alertdialog', { name: 'Delete file' });
    await confirm.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(confirm.getByRole('alert')).toContainText('failed: 500');
    await confirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(fileRow(page, 'wfh-form-schema.json')).toBeVisible();
    checks.push('Delete file');

    // Start on a published model.
    await mockApi(page, { method: 'POST', path: /\/start$/ }, 500, { message: reason });
    await page.goto(`/processes/${route(M.live)}`);
    await page.getByRole('button', { name: 'Start process' }).click();
    await expect(page.getByRole('alert')).toHaveText(reason);
    await expect(page).toHaveURL(new RegExp(`/processes/${route(M.live)}$`));
    checks.push('Start process');

    const saved = (await backendFetch(page, `/v1.0/m8flow/process-models/${route(M.draft)}`)).body as {
      display_name: string;
      files: { name: string }[];
    };
    expect(saved.display_name).toBe(M.draft.name);
    expect(saved.files.map((f) => f.name)).toContain('wfh-form-schema.json');

    logResult('PRC-49', {
      scenario: 'The server fails (mocked 500) for actions on the process model page',
      actions: checks,
      expected: 'Each window shows an error and stays open; the name and files do not change; Start stays on the page',
      actual: `Errors shown for ${checks.join(', ')}; server data unchanged`,
      messages: [reason, 'POST /v1.0/m8flow/process-models/…/copy failed: 500'],
    });
  });

  test('PRC-50: Another BPMN file can be set as primary, and the primary file cannot be deleted', async ({ page }) => {
    const second = `e2e-second-${stamp}.bpmn`;
    await seedProcessModelFile(page, second, scriptDiagram('x = 1'), route(M.prim));
    await page.goto(`/processes/${route(M.prim)}`);

    const oldPrimary = fileRow(page, SEED_PRIMARY_FILE);
    const newPrimary = fileRow(page, second);
    await expect(newPrimary.getByRole('button', { name: 'Set as primary' })).toHaveAttribute('title', 'Set as primary');
    await expect(fileRow(page, 'wfh-form-schema.json').getByRole('button', { name: 'Set as primary' })).toHaveCount(0);

    await newPrimary.getByRole('button', { name: 'Set as primary' }).click();
    await expect(newPrimary.getByText('Primary', { exact: true })).toBeVisible();
    await expect(newPrimary.getByRole('button', { name: 'Delete file' })).toHaveCount(0);
    await expect(oldPrimary.getByText('Primary', { exact: true })).toHaveCount(0);
    await expect(oldPrimary.getByRole('button', { name: 'Set as primary' })).toBeVisible();
    await expect(oldPrimary.getByRole('button', { name: 'Delete file' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Open in modeler' })).toHaveAttribute(
      'href',
      `/processes/${route(M.prim)}/modeler/${encodeURIComponent(second)}`,
    );

    const removePrimary = await backendFetch(
      page,
      `/v1.0/m8flow/process-models/${route(M.prim)}/files/${encodeURIComponent(second)}`,
      { method: 'DELETE' },
    );
    expect(removePrimary.status, 'deleting the primary file through the server').toBe(409);

    await oldPrimary.getByRole('button', { name: 'Set as primary' }).click();
    await expect(oldPrimary.getByText('Primary', { exact: true })).toBeVisible();

    logResult('PRC-50', {
      scenario: 'Change the primary BPMN file',
      actions: [`Set ${second} as primary`, 'Delete the primary file through the server', `Set ${SEED_PRIMARY_FILE} back`],
      expected: 'Only BPMN files offer "Set as primary"; the new primary has no delete and Open in modeler follows it; the server refuses to delete the primary',
      actual: `Primary moved to ${second} and back; server answered 409 for deleting the primary`,
    });
  });

  test('PRC-51: New DMN and JSON files open in the modeler, and every allowed upload type is listed', async ({
    page,
  }) => {
    await page.goto(`/processes/${route(M.kinds)}`);
    const before = await filesCount(page);
    const openAdd = async () => {
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.getByRole('button', { name: 'Add file', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Add file' });
      await expect(dialog.getByLabel('File name')).toHaveValue('');
      return dialog;
    };
    const chooseType = async (dialog: Locator, type: string) => {
      await dialog.getByRole('combobox', { name: 'File type' }).click();
      await page.getByRole('option', { name: type, exact: true }).click();
    };
    const listed: string[] = [];

    for (const [type, ext] of [['DMN', 'dmn'], ['JSON', 'json']] as const) {
      const dialog = await openAdd();
      await chooseType(dialog, type);
      await dialog.getByLabel('File name').fill(`e2e-new-${ext}-${stamp}`);
      await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/modeler/e2e-new-${ext}-${stamp}\\.${ext}$`));
      await page.goto(`/processes/${route(M.kinds)}`);
      await expect(fileRow(page, `e2e-new-${ext}-${stamp}.${ext}`)).toContainText(type);
      listed.push(`new ${type}`);
    }

    const uploads: [string, string, string][] = [
      ['xml', '<?xml version="1.0"?><e2e/>', 'XML'],
      ['svg', '<svg xmlns="http://www.w3.org/2000/svg"/>', 'SVG'],
      ['html', '<p>E2E</p>', 'HTML'],
      ['css', 'p { color: red; }', 'CSS'],
      ['txt', 'E2E text', 'TXT'],
    ];
    for (const [ext, content, label] of uploads) {
      const name = `e2e-up-${stamp}.${ext}`;
      const dialog = await openAdd();
      await chooseType(dialog, 'Upload');
      await dialog.getByLabel('Upload file').setInputFiles({ name, mimeType: 'text/plain', buffer: Buffer.from(content) });
      await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await expect(fileRow(page, name)).toContainText(label);
      listed.push(`.${ext} upload`);
    }
    expect(await filesCount(page)).toBe(before + 2 + uploads.length);

    logResult('PRC-51', {
      scenario: 'Every file type that can be created or uploaded',
      actions: ['New DMN', 'New JSON', 'Upload .xml, .svg, .html, .css, .txt'],
      expected: 'New DMN and JSON files open in the modeler; each upload is listed with its type; the file count goes up for each',
      actual: `${listed.join(', ')} listed; files ${before} -> ${before + 2 + uploads.length}`,
    });
  });

  test('PRC-52: Save as template offers Private, Tenant and Public, and splits tags at commas', async ({ page }) => {
    const name = `E2E Tenant Template ${stamp}`;
    await page.goto(`/processes/${route(M.prim)}`);
    await page.getByRole('button', { name: 'More actions', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Save as template', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Save as template' });

    await dialog.getByRole('combobox', { name: 'Visibility' }).click();
    const options: [string, string][] = [
      ['Private', 'Only you'],
      ['Tenant', 'Everyone in this tenant'],
      ['Public', 'Available to all tenants'],
    ];
    for (const [label, help] of options) {
      const option = page.getByRole('option', { name: new RegExp(`^${label}`) });
      await expect(option).toBeVisible();
      await expect(option).toContainText(help);
    }
    await page.getByRole('option', { name: /^Tenant/ }).click();
    await expect(dialog.getByRole('combobox', { name: 'Visibility' })).toContainText('Tenant');

    await dialog.getByLabel('Name', { exact: true }).fill(name);
    await dialog.getByLabel('Tags (comma-separated, optional)').fill('  e2e , mock ,, demo  ');
    await dialog.getByRole('button', { name: 'Create template' }).click();
    await expect(page).toHaveURL(/\/templates\/\d+/);
    const templateId = Number(/templates\/(\d+)/.exec(page.url())?.[1]);
    created.templates.push(templateId);
    const saved = (await backendFetch(page, `/v1.0/m8flow/templates/${templateId}`)).body as {
      visibility: string;
      tags: string[];
    };
    expect(saved.visibility).toBe('TENANT');
    expect(saved.tags).toEqual(['e2e', 'mock', 'demo']);

    logResult('PRC-52', {
      scenario: 'Template visibility and tags',
      actions: ['Open Visibility', 'Choose Tenant', 'Tags "  e2e , mock ,, demo  "', 'Create template'],
      expected: 'Three visibility options with their help text; template saved as Tenant with tags e2e, mock, demo',
      actual: `Template ${templateId}: visibility ${saved.visibility}, tags ${saved.tags.join(', ')}`,
      messages: options.map((o) => `${o[0]}: ${o[1]}`),
    });
  });

  test('PRC-53: An empty name in Edit identity or Copy falls back to the model id', async ({ page }) => {
    const copyId = `${M.ident.id}-nameless`;
    created.models.push(`${active.groupId}:${copyId}`);
    await page.goto(`/processes/${route(M.ident)}`);

    await page.getByRole('button', { name: 'More actions', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Edit identity', exact: true }).click();
    let dialog = page.getByRole('dialog', { name: 'Edit process model' });
    await dialog.getByLabel('Process model display name').fill('');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole('heading', { name: M.ident.id, exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'More actions', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Copy', exact: true }).click();
    dialog = page.getByRole('dialog', { name: 'Copy process model' });
    await dialog.getByLabel('Process model ID').fill(copyId);
    await dialog.getByLabel('Display name').fill('');
    await dialog.getByRole('button', { name: 'Copy process model' }).click();
    await expect(page).toHaveURL(new RegExp(`/processes/${active.groupId}:${copyId}$`));
    await expect(page.getByRole('heading', { name: copyId, exact: true })).toBeVisible();
    await expect(page.getByTestId('process-model-status')).toContainText('Draft');

    logResult('PRC-53', {
      scenario: 'Save without a name',
      actions: ['Edit identity with an empty name', 'Copy with an empty display name'],
      expected: 'The model and the copy are named after their id instead of being left without a name; a copy starts as Draft',
      actual: `Model now named "${M.ident.id}"; copy named "${copyId}" (Draft)`,
    });
  });

  test('PRC-54: A script unit test can be created and run from the model page, passing and failing', async ({
    page,
  }) => {
    await seedProcessModelFile(page, 'e2e-script.bpmn', scriptDiagram('x = 2'), route(M.scripts));
    await setPrimaryFile(page, route(M.scripts), 'e2e-script.bpmn');
    await page.goto(`/processes/${route(M.scripts)}`);
    const tests = page.locator('#tests');
    const create = async (expected: string) => {
      await tests.getByRole('button', { name: 'Create script unit test' }).click();
      const dialog = page.getByRole('dialog', { name: 'Create script unit test' });
      await dialog.getByLabel('Script task ID').fill(SCRIPT_TASK_ID);
      await dialog.getByLabel('Input JSON').fill('{}');
      await dialog.getByLabel('Expected output JSON').fill(expected);
      await dialog.getByRole('button', { name: 'Create', exact: true }).click();
      await expect(dialog).toHaveCount(0);
    };
    const runLast = async () => {
      await tests.getByRole('button', { name: 'Run', exact: true }).last().click();
      const result = page.getByRole('dialog', { name: 'Script unit test' });
      await expect(result).toBeVisible();
      const text = (await result.innerText()).replace(/\s+/g, ' ');
      await result.getByRole('button', { name: 'Close', exact: true }).last().click();
      return text;
    };

    await expect(tests.getByText('No script unit tests yet.')).toBeVisible();
    await create('{"x": 2}');
    await expect(tests.getByText(SCRIPT_TASK_ID, { exact: true })).toHaveCount(1);
    const pass = await runLast();
    expect(pass).toContain('Passed.');

    await create('{"x": 3}');
    await expect(tests.getByText(SCRIPT_TASK_ID, { exact: true })).toHaveCount(2);
    const fail = await runLast();
    expect(fail).not.toContain('Passed.');

    logResult('PRC-54', {
      scenario: 'Script unit tests on the model page (script sets x = 2)',
      actions: ['Create test expecting x = 2', 'Run', 'Create test expecting x = 3', 'Run'],
      expected: 'Both tests are listed; the first passes, the second does not',
      actual: `First: "Passed."; second: "${fail.replace('Script unit test', '').replace('Close', '').trim()}"`,
      messages: ['No script unit tests yet.', 'Passed.'],
    });
  });

  test('PRC-55: A real BPMN test file runs and reports passing and failing cases', async ({ page }) => {
    // The BPMN test runner follows each element's <outgoing> flows, so the diagram must list them
    // (diagrams saved by the modeler always do).
    const diagram = 'e2e-approval.bpmn';
    const testFile = 'test_e2e-approval.json';
    await seedProcessModelFile(page, diagram, userTaskDiagram(), route(M.bpmntest));
    const cases = {
      e2e_pass: { tasks: { [USER_TASK_ID]: { data: [{ reason: 'Home' }] } }, expected_output_json: { reason: 'Home' } },
      e2e_fail: { tasks: { [USER_TASK_ID]: { data: [{ reason: 'Home' }] } }, expected_output_json: { reason: 'Office' } },
    };
    await seedProcessModelFile(page, testFile, JSON.stringify(cases, null, 2), route(M.bpmntest));
    await page.goto(`/processes/${route(M.bpmntest)}`);
    await expect(fileRow(page, testFile)).toContainText('BPMN test');

    const tests = page.locator('#tests');
    await tests.getByRole('button', { name: 'Run BPMN tests' }).click();
    const results = page.getByRole('dialog', { name: 'BPMN test results' });
    await expect(results).toContainText('1 failed, 1 passed.');
    await expect(results).toContainText('e2e_fail — Expected output did not match actual output.');
    await results.getByRole('button', { name: 'Close', exact: true }).last().click();

    // A user task without test data cannot run.
    await seedProcessModelFile(
      page,
      testFile,
      JSON.stringify({ e2e_missing: { tasks: {}, expected_output_json: {} } }),
      route(M.bpmntest),
    );
    await page.reload();
    await tests.getByRole('button', { name: 'Run BPMN tests' }).click();
    // Refused either for the whole run (error under Tests) or as a failed case in the results.
    const refusedRun = tests.getByRole('alert');
    await expect(refusedRun.or(results)).toBeVisible();
    let missing: string;
    if (await refusedRun.isVisible()) {
      await expect(refusedRun).toContainText('failed: 400');
      missing = await refusedRun.innerText();
    } else {
      await expect(results).toContainText('1 failed, 0 passed.');
      missing = (await results.innerText()).replace(/\s+/g, ' ');
      await results.getByRole('button', { name: 'Close', exact: true }).last().click();
    }

    logResult('PRC-55', {
      scenario: `Run the BPMN test file ${testFile} for ${diagram} (no mocking)`,
      actions: ['Run with one passing and one failing case', 'Run with a case missing the user task data'],
      expected: 'Results show 1 failed, 1 passed with the reason; missing task data is refused with an error',
      actual: 'Results: "1 failed, 1 passed." with "Expected output did not match actual output."; missing data refused',
      messages: ['1 failed, 1 passed.', 'Expected output did not match actual output.', missing],
    });
  });
});

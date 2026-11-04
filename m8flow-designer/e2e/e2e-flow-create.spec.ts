import { readFileSync } from 'node:fs';

import { expect, test, type Page } from '@playwright/test';

import { editorCredentials, reviewerCredentials, submitterCredentials, useSession } from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import { createMockModel, setModelStatus } from './helpers/mockCatalog';
import {
  LANE,
  completeTask,
  flowBpmn,
  formSchema,
  hasTaskFor,
  instanceDetail,
  postMultipart,
  processIdFor,
  startInstance,
  startStatus,
  submitTask,
  taskData,
  taskTitle,
  useFlowCatalog,
  waitForStatus,
  waitForTask,
  withPage,
  zipFiles,
  type FlowCatalog,
} from './helpers/processFlow';
import { fileRow, logResult, slugify } from './helpers/processesPage';
import { seedProcessModelFile } from './helpers/seedFixture';
import { urlPathEndsWith } from './helpers/urls';

/**
 * Process flow: ways to create a process and run it.
 *
 * FLW-06  default model from "New process model" runs to Complete
 * FLW-07  BPMN uploaded with Add file > Upload runs end to end
 * FLW-08  "Single Approval" sample template, approved path
 * FLW-09  "Single Approval" sample template, rejected path
 * FLW-10  "Two-Step Leave Approval" sample template (email steps need SMTP)
 * FLW-11  template imported from a ZIP runs end to end
 * FLW-12  invalid template ZIPs are refused
 * FLW-13  malformed / unsupported BPMN is refused on upload
 * FLW-14  an uploaded JSON form schema drives the task form
 * FLW-15  a task whose form schema file is missing still opens and submits
 * FLW-16  pausing or unpublishing a model does not block its waiting task
 *
 * Everything is created in a mock group for this file and deleted afterwards.
 */

const APPROVAL_FORM = 'e2e-flow-review-schema.json';
const approvalForm = readFileSync(new URL(`./fixtures/e2e-flow/${APPROVAL_FORM}`, import.meta.url), 'utf-8');
const approvalStep = { id: 'Activity_approve_request', name: 'E2E Approve Request', lane: LANE.approvers, form: APPROVAL_FORM };

const FIELDS_FORM = 'e2e-flow-fields-schema.json';
const fieldsForm = formSchema(
  'E2E request',
  {
    request_title: { type: 'string', title: 'Request title', minLength: 3 },
    amount: { type: 'number', title: 'Amount' },
    due_date: { type: 'string', title: 'Due date', format: 'date' },
    priority: { type: 'string', title: 'Priority', enum: ['Low', 'High'] },
    urgent: { type: 'boolean', title: 'Urgent' },
  },
  ['request_title', 'amount', 'priority'],
);

const flow = useFlowCatalog(test, 'flowc', {
  fields: { name: 'E2E Fields', bpmn: { steps: [{ ...approvalStep, form: FIELDS_FORM }] }, files: { [FIELDS_FORM]: fieldsForm } },
  noschema: { name: 'E2E No Schema', bpmn: { steps: [{ ...approvalStep, form: 'e2e-missing-schema.json' }] } },
  paused: { name: 'E2E Paused Later', bpmn: { steps: [approvalStep] }, files: { [APPROVAL_FORM]: approvalForm } },
  draft: { name: 'E2E Unpublished Later', bpmn: { steps: [approvalStep] }, files: { [APPROVAL_FORM]: approvalForm } },
});

function approvalBpmn(catalog: FlowCatalog, key: string): string {
  return flowBpmn({ processId: processIdFor('flowc', key, catalog.stamp), name: `E2E ${key}`, steps: [approvalStep] });
}

/** Starts from the model page as the logged-in user; returns the instance id. */
async function startFromModelPage(page: Page, route: string): Promise<number> {
  await page.goto(`/processes/${route}`);
  await page.getByRole('button', { name: 'Start process', exact: true }).click();
  await expect(page).toHaveURL((url) => /^\/process-instances\/\d+$/.test(url.pathname));
  const id = Number(new URL(page.url()).pathname.split('/').pop());
  flow.track.instances.push(id);
  return id;
}

type TemplateRow = { id: number; templateKey: string; name: string; isPublished: boolean; files?: { fileName?: string; name?: string }[] };

async function templateByKey(page: Page, key: string): Promise<TemplateRow | undefined> {
  const result = await backendFetch(page, `/v1.0/m8flow/templates?template_key=${encodeURIComponent(key)}`);
  if (result.status !== 200) return undefined;
  const rows = ((result.body as { results?: TemplateRow[] }).results ?? []).filter((t) => t.templateKey === key);
  return rows[0];
}

/** Creates (as editor) a published model from a template and returns its route. */
async function modelFromTemplate(page: Page, templateId: number, modelId: string, name: string): Promise<string> {
  const result = await backendFetch(page, `/v1.0/m8flow/templates/${templateId}/create-process-model`, {
    method: 'POST',
    data: { process_group_id: flow.groupId, process_model_id: modelId, display_name: name },
  });
  const code = (result.body as { error_code?: string } | null)?.error_code;
  const hint = code === 'file_copy_failed'
    ? 'ENVIRONMENT: the template is in the database but its files are missing from the server template storage (reload the sample templates or reset the stack). '
    : '';
  expect(result.status, `${hint}create model from template: ${JSON.stringify(result.body)}`).toBeLessThan(300);
  const route = `${flow.groupId}:${modelId}`;
  flow.track.models.push(route);
  await setModelStatus(page, route, 'published');
  return route;
}

/** True when the BPMN element (e.g. an end event) has completed in the instance. */
async function reached(page: Page, id: number, bpmnId: string): Promise<boolean> {
  const detail = await instanceDetail(page, id);
  return detail.tasks.some((t) => t.bpmn_identifier === bpmnId && /^completed$/i.test(t.state));
}

test.describe('Process flow: ways to create and run a process', { tag: ['@workflow', '@import'] }, () => {
  test('FLW-06: A default model created with "New process model" can be published and run', async ({ page, browser }) => {
    await useSession(page, editorCredentials());
    const name = `E2E Default ${flow.stamp}`;
    await page.goto(`/processes?group=${encodeURIComponent(flow.groupId)}`);
    await page.getByRole('button', { name: 'New process model', exact: true }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New process model' });
    await expect(dialog.getByRole('combobox', { name: 'Process group' })).toContainText(flow.groupName);
    await dialog.getByLabel('Display name').fill(name);
    await expect(dialog.getByLabel('Identifier')).toHaveValue(slugify(name));
    await dialog.getByRole('button', { name: 'Create process model' }).click();
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
    const route = `${flow.groupId}:${slugify(name)}`;
    flow.track.models.push(route);
    const status = page.getByTestId('process-model-status');
    await expect(status).toContainText('Draft');
    await page.getByRole('button', { name: 'Publish', exact: true }).click();
    await expect(status).toContainText('Published');

    // The default diagram is start -> "Task" (a plain BPMN task) -> end. M8Flow
    // treats the plain task as a manual step for the person who started it.
    const result = await withPage(browser, submitterCredentials(), async (sub) => {
      const id = await startFromModelPage(sub, route);
      const first = await waitForStatus(sub, id, ['complete', 'user_input_required']);
      let manualStep = 'none';
      if (first.status === 'user_input_required') {
        const task = await completeTask(sub, id, {}, 'Task');
        manualStep = `"${taskTitle(task)}" completed by the starter`;
      }
      const done = await waitForStatus(sub, id, 'complete');
      return { id, status: done.status, manualStep };
    });
    const reviewerTask = await withPage(browser, reviewerCredentials(), (rev) => hasTaskFor(rev, result.id));
    expect(reviewerTask, 'the reviewer gets no task from the default model').toBe(false);

    logResult('FLW-06', {
      scenario: 'Default process model (start -> plain task -> end)',
      actions: ['Login to M8Flow as Editor', `New process model "${name}"`, 'Publish', 'Submitter clicks "Start process"'],
      expected: 'Created as Draft, published; the instance completes (the plain "Task" step, if any, goes to the starter only)',
      actual: `Instance #${result.id} is "${result.status}"; manual step: ${result.manualStep}; no task for the reviewer`,
    });
  });

  test('FLW-07: A BPMN file uploaded with Add file > Upload runs end to end', async ({ page, browser }) => {
    await useSession(page, editorCredentials());
    const modelId = `e2e-upload-${flow.stamp}`;
    const route = await createMockModel(page, { group_id: flow.groupId, id: modelId, display_name: `E2E Upload ${flow.stamp}` });
    flow.track.models.push(route);
    const bpmnName = 'e2e-uploaded.bpmn';

    // The form JSON is only a prerequisite: seed it through the API. The BPMN
    // upload is what this test checks, so it goes through the UI.
    await seedProcessModelFile(page, APPROVAL_FORM, approvalForm, route);
    await page.goto(`/processes/${route}`);
    await page.getByRole('button', { name: 'Add file', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Add file' });
    await dialog.getByRole('combobox', { name: 'File type' }).click();
    await page.getByRole('option', { name: 'Upload', exact: true }).click();
    await expect(page.getByRole('option', { name: 'Upload', exact: true })).toHaveCount(0);
    await dialog.getByLabel('File name').fill(bpmnName);
    await dialog
      .getByLabel('Upload file')
      .setInputFiles({ name: bpmnName, mimeType: 'application/xml', buffer: Buffer.from(approvalBpmn(flow, 'upload')) });
    await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    // Adding a BPMN may open it in the modeler; come back to the model page.
    await page.goto(`/processes/${route}`);
    await expect(fileRow(page, bpmnName)).toBeVisible();
    await expect(fileRow(page, APPROVAL_FORM)).toBeVisible();
    await fileRow(page, bpmnName).getByRole('button', { name: 'Set as primary' }).click();
    await expect(fileRow(page, bpmnName).getByRole('button', { name: 'Set as primary' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Publish', exact: true }).click();
    await expect(page.getByTestId('process-model-status')).toContainText('Published');

    const id = await withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, route));
    await withPage(browser, reviewerCredentials(), (rev) => completeTask(rev, id, { approval_note: `E2E ${flow.stamp}` }));
    const done = await waitForStatus(page, id, 'complete');

    logResult('FLW-07', {
      scenario: 'BPMN and form uploaded through the UI',
      actions: ['Seed the form JSON (API)', 'Add file > Upload the BPMN', 'Set as primary', 'Publish', 'Submitter starts, reviewer submits'],
      expected: 'The uploaded BPMN is listed and set as primary; the instance completes after the approval',
      actual: `Instance #${id} "${done.status}"`,
    });
  });

  for (const path of [
    { id: 'FLW-08', decision: 'Approved', option: 'Approve', end: 'Event_approved', other: 'Event_rejected' },
    { id: 'FLW-09', decision: 'Rejected', option: 'Reject', end: 'Event_rejected', other: 'Event_approved' },
  ]) {
    test(`${path.id}: "Single Approval" sample template runs the ${path.decision.toLowerCase()} path`, async ({ page, browser }) => {
      await useSession(page, editorCredentials());
      const template = await templateByKey(page, 'single-approval');
      test.skip(!template, 'The "Single Approval" sample template is not loaded (M8FLOW_LOAD_SAMPLE_TEMPLATES).');
      const route = await modelFromTemplate(page, template!.id, `e2e-wfh-${path.decision.toLowerCase()}-${flow.stamp}`, `E2E WFH ${path.decision} ${flow.stamp}`);

      const id = await withPage(browser, submitterCredentials(), async (sub) => {
        const instanceId = await startFromModelPage(sub, route);
        const task = await waitForTask(sub, instanceId, 'Submit WFH Request');
        await sub.goto(`/task-review/${task.id}`);
        await sub.getByLabel('WFH Date').fill('2026-12-01');
        await sub.getByLabel('Reason for WFH').fill(`E2E reason for working from home ${flow.stamp}`);
        await sub.getByRole('button', { name: 'Submit', exact: true }).click();
        await expect(sub).toHaveURL(urlPathEndsWith('/task-review'));
        return instanceId;
      });

      await withPage(browser, reviewerCredentials(), async (rev) => {
        const task = await waitForTask(rev, id, 'Review WFH Request');
        await rev.goto(`/task-review/${task.id}`);
        await rev.getByRole('combobox', { name: /^Decision/ }).click();
        await rev.getByRole('option').filter({ hasText: path.option }).first().click();
        await rev.getByRole('button', { name: 'Submit', exact: true }).click();
        await expect(rev).toHaveURL(urlPathEndsWith('/task-review'));
      });

      const done = await waitForStatus(page, id, 'complete');
      expect(await reached(page, id, path.end), `end event ${path.end} completed`).toBe(true);
      expect(await reached(page, id, path.other), `end event ${path.other} not reached`).toBe(false);

      logResult(path.id, {
        scenario: `Single Approval template, ${path.decision} path`,
        actions: ['Create model from the template and publish', 'Submitter starts and submits the WFH request', `Reviewer chooses "${path.option}"`],
        expected: `Request goes to the submitter, review to the reviewer; instance Complete via ${path.end}`,
        actual: `Instance #${id} "${done.status}", ended at ${path.end}`,
      });
    });
  }

  test('FLW-10: "Two-Step Leave Approval" sample template runs manager then HR approval', async ({ page, browser }) => {
    test.setTimeout(150_000);
    await useSession(page, editorCredentials());
    const template = await templateByKey(page, 'two-step-leave-approval-with-email-notifications');
    test.skip(!template, 'The "Two-Step Leave Approval" sample template is not loaded.');
    const route = await modelFromTemplate(page, template!.id, `e2e-leave-${flow.stamp}`, `E2E Leave ${flow.stamp}`);

    const id = await withPage(browser, submitterCredentials(), async (sub) => {
      const instanceId = await startInstance(sub, flow, route);
      await completeTask(sub, instanceId, {
        employee_name: 'E2E Tester',
        email: 'e2e-leave@example.test',
        start_date: '2026-12-01',
        end_date: '2026-12-02',
        reason: `E2E leave request ${flow.stamp}`,
        leave_type: 'Casual Leave',
      }, 'Submit Leave Request');
      return instanceId;
    });

    const notes = await withPage(browser, reviewerCredentials(), async (rev) => {
      const manager = await waitForTask(rev, id, 'Review Leave Request');
      // HR review must not exist before the manager decides.
      expect(await hasHrTask(rev, id), 'HR review is not created before the manager review').toBe(false);
      expect((await submitTask(rev, manager.id, { approval_status: 'approved' })).status).toBeLessThan(300);
      const hr = await waitForTask(rev, id, 'HR Review Leave Request');
      const hrSubmit = await submitTask(rev, hr.id, { hr_approval_status: 'approved' });
      return { managerTask: manager.id, hrTask: hr.id, hrSubmit };
    });

    // The approve path ends with an SMTP email step that runs inside the HR
    // submit: with a working SMTP connector the submit succeeds and the
    // instance completes; without one (the test environment) the submit
    // returns 500 and the instance stays at the HR task (or shows Error).
    const done = await waitForStatus(page, id, notes.hrSubmit.status >= 300 ? ['error', 'user_input_required'] : ['complete']);
    if (notes.hrSubmit.status >= 300) {
      expect(notes.hrSubmit.status, 'a failed HR submit is a server error from the email step').toBe(500);
      test.info().annotations.push({ type: 'needs-smtp', description: `Email step failed: ${JSON.stringify(notes.hrSubmit.body)}` });
    } else {
      expect(done.status).toBe('complete');
    }

    logResult('FLW-10', {
      scenario: 'Two-Step Leave Approval template (manager, then HR)',
      actions: ['Create model from the template', 'Submitter submits the leave form', 'Reviewer approves as manager', 'Reviewer approves as HR'],
      expected: 'HR review appears only after the manager review; the instance ends Complete (SMTP set up), or the HR submit fails and the instance stays at HR review or shows Error (no SMTP)',
      actual: `Manager task #${notes.managerTask}, then HR task #${notes.hrTask} (submit ${notes.hrSubmit.status}); instance #${id} "${done.status}"${done.error_message ? ` (${done.error_message})` : ''}`,
    });
  });

  test('FLW-11: A template imported from a ZIP file is used to create and run a process', async ({ page, browser }) => {
    await useSession(page, editorCredentials());
    const key = `e2e-flow-zip-${flow.stamp}`;
    const templateName = `E2E Flow Zip ${flow.stamp}`;
    const zip = zipFiles({ 'e2e-zip-approval.bpmn': approvalBpmn(flow, 'zip'), [APPROVAL_FORM]: approvalForm });

    await page.goto('/templates');
    await page.getByRole('button', { name: 'Import', exact: true }).first().click();
    const dialog = page.getByRole('dialog', { name: 'Import template' });
    await dialog.locator('#import-file').setInputFiles({ name: `${key}.zip`, mimeType: 'application/zip', buffer: zip });
    await dialog.locator('#import-key').fill(key);
    await dialog.locator('#import-name').fill(templateName);
    await dialog.getByRole('button', { name: 'Import', exact: true }).click();
    await expect(dialog).toHaveCount(0);

    let template: TemplateRow | undefined;
    await expect.poll(async () => Boolean((template = await templateByKey(page, key))), { timeout: 15_000 }).toBe(true);
    flow.track.templates.push(template!.id);
    const files = (template!.files ?? []).map((f) => f.fileName ?? f.name ?? '');
    if (!template!.isPublished) {
      const published = await backendFetch(page, `/v1.0/m8flow/templates/${template!.id}`, { method: 'PUT', data: { is_published: true } });
      expect(published.status, 'publish the imported template').toBeLessThan(300);
    }
    const route = await modelFromTemplate(page, template!.id, `e2e-from-zip-${flow.stamp}`, `E2E From Zip ${flow.stamp}`);

    const id = await withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, route));
    await withPage(browser, reviewerCredentials(), (rev) => completeTask(rev, id, { approval_note: `E2E zip ${flow.stamp}` }));
    const done = await waitForStatus(page, id, 'complete');

    logResult('FLW-11', {
      scenario: 'ZIP template import -> process model -> run',
      actions: ['Templates > Import the ZIP', 'Publish the template', 'Create a process model from it', 'Run and approve'],
      expected: 'The template is imported with its files; the model created from it runs to Complete',
      actual: `Template #${template!.id} (${files.join(', ') || 'files listed'}); instance #${id} "${done.status}"`,
    });
  });

  test('FLW-12: Invalid template ZIP files are refused', async ({ page }) => {
    await useSession(page, editorCredentials());
    const tryImport = async (label: string, buffer: Buffer) => {
      const key = `e2e-bad-zip-${label}-${flow.stamp}`;
      const result = await postMultipart(
        page,
        '/v1.0/m8flow/templates/import',
        { name: `${key}.zip`, mimeType: 'application/zip', buffer },
        { 'X-Template-Key': key, 'X-Template-Name': `E2E Bad Zip ${label} ${flow.stamp}` },
      );
      const created = await templateByKey(page, key);
      if (created) flow.track.templates.push(created.id);
      return { ...result, created, message: JSON.stringify(result.body) };
    };

    const notZip = await tryImport('text', Buffer.from('this is not a zip file'));
    expect(notZip.status).toBe(400);
    expect(notZip.message).toContain('Invalid zip file');
    expect(notZip.created).toBeFalsy();

    const noBpmn = await tryImport('nobpmn', zipFiles({ 'readme.md': '# no diagram here' }));
    expect(noBpmn.status).toBe(400);
    expect(noBpmn.message).toContain('at least one .bpmn file');
    expect(noBpmn.created).toBeFalsy();

    // A ZIP whose BPMN is broken may be stored; it must not produce a runnable model.
    const broken = await tryImport('broken', zipFiles({ 'broken.bpmn': '<bpmn:definitions><not-closed>' }));
    let brokenOutcome = `import refused (${broken.status})`;
    if (broken.status < 300 && broken.created) {
      const create = await backendFetch(page, `/v1.0/m8flow/templates/${broken.created.id}/create-process-model`, {
        method: 'POST',
        data: { process_group_id: flow.groupId, process_model_id: `e2e-broken-${flow.stamp}`, display_name: `E2E Broken ${flow.stamp}` },
      });
      if (create.status < 300) flow.track.models.push(`${flow.groupId}:e2e-broken-${flow.stamp}`);
      brokenOutcome = `import accepted; creating a model from it returned ${create.status}`;
      expect(create.status, 'a model is not created from a broken BPMN').toBeGreaterThanOrEqual(400);
    }

    logResult('FLW-12', {
      scenario: 'Import invalid template ZIP files',
      actions: ['Import a text file named .zip', 'Import a ZIP without BPMN', 'Import a ZIP with a broken BPMN'],
      expected: 'The first two are refused with a clear message and no template; the broken one never becomes a runnable model',
      actual: `text: ${notZip.status}; no BPMN: ${noBpmn.status}; broken BPMN: ${brokenOutcome}`,
      messages: [notZip.message, noBpmn.message],
    });
  });

  test('FLW-13: Malformed or unsupported BPMN is refused when uploaded', async ({ page }) => {
    await useSession(page, editorCredentials());
    const route = await createMockModel(page, { group_id: flow.groupId, id: `e2e-badbpmn-${flow.stamp}`, display_name: `E2E Bad BPMN ${flow.stamp}` });
    flow.track.models.push(route);
    const unsupported = flowBpmn({ processId: processIdFor('flowc', 'callact', flow.stamp), name: 'x', steps: [approvalStep] }).replace(
      '<bpmn:endEvent',
      '<bpmn:callActivity id="Activity_call" calledElement="Process_missing" /><bpmn:endEvent',
    );
    const messages: string[] = [];
    await page.goto(`/processes/${route}`);
    for (const [fileName, content] of [
      ['e2e-malformed.bpmn', '<?xml version="1.0"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"><bpmn:process id="p">'],
      ['e2e-call-activity.bpmn', unsupported],
    ] as const) {
      await page.getByRole('button', { name: 'Add file', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Add file' });
      await dialog.getByRole('combobox', { name: 'File type' }).click();
      await page.getByRole('option', { name: 'Upload', exact: true }).click();
      await expect(page.getByRole('option', { name: 'Upload', exact: true })).toHaveCount(0);
      await dialog.getByLabel('File name').fill(fileName);
      await dialog.getByLabel('Upload file').setInputFiles({ name: fileName, mimeType: 'application/xml', buffer: Buffer.from(content) });
      await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
      const alert = dialog.getByRole('alert');
      await expect(alert).toBeVisible();
      messages.push(`${fileName}: ${(await alert.innerText()).trim()}`);
      await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await expect(fileRow(page, fileName)).toHaveCount(0);
    }

    logResult('FLW-13', {
      scenario: 'Upload malformed and unsupported BPMN',
      actions: ['Add file > Upload malformed XML', 'Add file > Upload BPMN with a Call Activity'],
      expected: 'Each upload is refused with a message in the dialog; neither file is added',
      actual: 'Both refused; files not listed',
      messages,
    });
  });

  test('FLW-14: An uploaded JSON form schema drives the task form', async ({ page, browser }) => {
    const m = flow.model('fields');
    const id = await withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, m.route));
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    await page.goto(`/task-review/${task.id}`);
    await expect(page.getByRole('heading', { level: 1, name: taskTitle(task), exact: true })).toBeVisible();

    await expect(page.getByLabel('Request title')).toHaveAttribute('type', 'text');
    await expect(page.getByLabel('Amount')).toHaveAttribute('type', 'number');
    await expect(page.getByLabel('Due date')).toHaveAttribute('type', 'date');
    await expect(page.getByRole('checkbox', { name: 'Urgent' })).toBeVisible();
    for (const label of ['Request title', 'Amount', 'Priority']) {
      await expect(page.locator('label').filter({ hasText: label }).first()).toContainText('*');
    }

    await page.getByLabel('Request title').fill('New laptop');
    await page.getByLabel('Amount').fill('1250.5');
    await page.getByLabel('Due date').fill('2026-12-15');
    await page.getByLabel('Priority').click();
    await page.getByRole('option', { name: 'High', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Urgent' }).check();
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));

    const done = await withPage(browser, editorCredentials(), async (ed) => ({
      detail: await waitForStatus(ed, id, 'complete'),
      data: await taskData(ed, id, 'Activity_approve_request'),
    }));
    expect(done.data).toMatchObject({ request_title: 'New laptop', amount: 1250.5, due_date: '2026-12-15', priority: 'High', urgent: true });

    logResult('FLW-14', {
      scenario: 'Task form from an uploaded JSON schema with several field types',
      actions: ['Open the task', 'Check each field and its input type', 'Fill and submit'],
      expected: 'Text, number, date, choice and yes/no fields render with required marks; values are saved with the right types',
      actual: `Saved: ${JSON.stringify(done.data)}; instance "${done.detail.status}"`,
    });
  });

  test('FLW-15: A task whose form schema file is missing still opens and can be submitted', async ({ page, browser }) => {
    const m = flow.model('noschema');
    const id = await withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, m.route));
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    await page.goto(`/task-review/${task.id}`);
    await expect(page.getByRole('heading', { name: 'Task Form', exact: true })).toBeVisible();
    await expect(page.getByRole('textbox')).toHaveCount(0);
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    // Reviewers cannot read Process Instances; check the status as the editor.
    const done = await withPage(browser, editorCredentials(), (ed) => waitForStatus(ed, id, 'complete'));

    logResult('FLW-15', {
      scenario: 'Task points to a schema file that is not in the model',
      actions: ['Open the task', 'Submit the empty form'],
      expected: 'The task opens with an empty form (no crash) and can be submitted',
      actual: `Empty form shown; instance #${id} "${done.status}"`,
    });
  });

  for (const state of [
    { id: 'FLW-16a', key: 'paused', status: 'paused' as const, label: 'paused' },
    { id: 'FLW-16b', key: 'draft', status: 'draft' as const, label: 'unpublished (Draft)' },
  ]) {
    test(`${state.id}: A waiting task can still be completed after the model is ${state.label}`, async ({ page, browser }) => {
      const m = flow.model(state.key);
      const id = await withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, m.route));
      await useSession(page, editorCredentials());
      await setModelStatus(page, m.route, state.status);

      await withPage(browser, reviewerCredentials(), (rev) => completeTask(rev, id, { approval_note: 'Still works' }));
      const done = await waitForStatus(page, id, 'complete');
      const newStart = await withPage(browser, submitterCredentials(), (sub) => startStatus(sub, m.route));
      expect(newStart, 'a new start is refused while the model is not published').toBe(409);

      logResult(state.id, {
        scenario: `Model ${state.label} while an instance waits for approval`,
        actions: ['Submitter starts', `Editor sets the model to ${state.label}`, 'Reviewer submits', 'Submitter tries to start again'],
        expected: 'The waiting task can still be completed; new starts are refused',
        actual: `Instance #${id} "${done.status}"; new start returned ${newStart}`,
      });
    });
  }
});

async function hasHrTask(page: Page, instanceId: number): Promise<boolean> {
  const result = await backendFetch(page, '/v1.0/m8flow/task-review?per_page=100');
  const rows = (result.body as { results?: { process_instance_id: number; task_title: string | null; task_name: string }[] }).results ?? [];
  return rows.some((t) => t.process_instance_id === instanceId && taskTitle(t) === 'HR Review Leave Request');
}

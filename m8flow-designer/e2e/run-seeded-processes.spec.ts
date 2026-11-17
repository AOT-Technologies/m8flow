import { expect, test, type Browser, type Locator, type Page } from '@playwright/test';

import {
  editorCredentials,
  reviewerCredentials,
  submitterCredentials,
  tenantAdminCredentials,
  type DesignerPersona,
} from './helpers/auth';
import { backendFetch } from './helpers/backendApi';
import { deleteInstanceIds, startMockInstance } from './helpers/mockCatalog';
import { logResult } from './helpers/processesPage';
import {
  closeRolePages,
  instanceDetail,
  startStatus,
  taskData,
  taskTitle,
  withPage,
  type InstanceDetail,
  type TaskItem,
  waitForInstancePage,
} from './helpers/processFlow';
import {
  catalogPaths,
  seededTemplateId,
  templateFiles,
  templateKey,
  hasPostgresProfile,
  humanTaskIds,
  postgresConnection,
  seededModel,
  templateFileNames,
  usesPostgres,
  type CatalogPath,
  type SeededModelCopy,
} from './helpers/seedCatalog';
import { urlPathEndsWith } from './helpers/urls';
import { loadBaseline, seedBaselineOnce } from './seed/seed';

/**
 * Seeded catalog run check (M8F-677). Every route in the paths.json files of
 * the seeded catalog (e2e/seed/catalog/<model>/ and .../templates/<key>/) is run
 * on the seeded model itself, through the screens as a person does: the
 * submitter clicks "Start process" on the model page, and each task is opened
 * in Task Review by whoever the server gives it (submitter for the Submitters
 * lane, reviewer for Approvers, tenant admin for Administrators), its form is
 * filled with the answers from the path and the right button is clicked
 * (Approve / Reject / Publish / ... for a decision, else Submit). Then the test checks what the path expects: the tasks
 * worked, the ends and elements reached or not reached, and the data at the end.
 * Tasks in "leave" are never submitted, so a timer takes over.
 * The same paths are checked on the engine alone by e2e/seed/tools/validate_catalog.py.
 * Instances started here are deleted afterwards; the seeded models stay.
 *
 * ORD-04 also records exactly what the page sends for the order form (it found the data-object bug).
 */

const WORKERS: DesignerPersona[] = [submitterCredentials(), reviewerCredentials(), tenantAdminCredentials()];

/** Instances started by this file, deleted afterwards (as tenant admin). */
const started: number[] = [];

/** The user's Task Review inbox; empty when the role has none (403). */
async function inbox(page: Page): Promise<TaskItem[]> {
  const result = await backendFetch(page, '/v1.0/m8flow/task-review?per_page=100');
  if (result.status === 403) return [];
  expect(result.status, 'GET /task-review').toBe(200);
  return (result.body as { results: TaskItem[] }).results;
}

/**
 * "@now+5s" in an answer becomes a date-time 5 seconds from now; "@date+5s" and
 * "@time+5s" its date (YYYY-MM-DD) and its time (HH:MM:SS+00:00), in UTC.
 */
function answerValue(value: unknown): unknown {
  if (typeof value === 'string') {
    const m = value.match(/^@(now|date|time)\+(\d+)s$/);
    if (m) {
      const iso = new Date(Date.now() + Number(m[2]) * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
      if (m[1] === 'date') return iso.slice(0, 10);
      if (m[1] === 'time') return `${iso.slice(11, 19)}+00:00`;
      return iso;
    }
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, answerValue(v)]));
  }
  return value;
}


type FormField = { type?: string; title?: string; format?: string; enum?: unknown[]; enumNames?: string[]; oneOf?: { const?: unknown; title?: string }[] };
type TaskDetail = { form?: { schema?: { properties?: Record<string, FormField> } }; outcomes?: { value: string; label: string }[] };

/**
 * The form field a person finds by its title. Every field on the Task Review form is a
 * <label> whose first <span> shows the title (plus " *" when required), so the field is
 * the label whose title text equals `title` -- compared as plain text, no pattern built from it.
 */
async function fieldByTitle(page: Page, title: string): Promise<Locator> {
  const labels = page.locator('label').filter({ hasText: title });
  const count = await labels.count();
  for (let i = 0; i < count; i += 1) {
    const label = labels.nth(i);
    const heading = (await label.locator(':scope > span').first().textContent()) ?? '';
    if (heading.trim().replace(/\s*\*$/, '') === title) return label;
  }
  throw new Error(`no form field titled "${title}" on the Task Review page`);
}

/** The text of the select option for `value` (oneOf title, enumNames entry, or the value itself). */
function optionLabel(field: FormField, value: unknown): string {
  const one = field.oneOf?.find((o) => o.const === value);
  if (one?.title) return one.title;
  const index = (field.enum ?? []).indexOf(value);
  if (index >= 0 && field.enumNames?.at(index)) return field.enumNames.at(index)!;
  return String(value);
}

/** Fills one form field on the Task Review page the way a person does. */
async function fillField(page: Page, key: string, field: FormField, value: unknown): Promise<void> {
  const title = field.title ?? key;
  const box = await fieldByTitle(page, title);
  if (field.type === 'boolean') {
    await box.getByRole('checkbox').setChecked(Boolean(value));
  } else if (field.enum || field.oneOf) {
    await box.getByRole('combobox').click();
    await page.getByRole('option', { name: optionLabel(field, value), exact: true }).click();
  } else if (field.format === 'date') {
    await box.locator('input').fill(String(value));
  } else if (field.type === 'number' || field.type === 'integer') {
    await box.getByRole('spinbutton').fill(String(value));
  } else {
    await box.getByRole('textbox').fill(String(value));
  }
}

type PageSubmit = { status: number; body: Record<string, unknown> | null; button: string; alert?: string };

/**
 * Works one task through the Task Review page: opens it, fills the form fields
 * from the answer, and clicks the button a person would (the decision button
 * named after the answer's "outcome", else Submit / Continue). The form and the
 * buttons are read from the task's detail first, only to know what is on the page.
 */
async function submitOnPage(page: Page, taskId: number, answer: Record<string, unknown>): Promise<PageSubmit> {
  const detailResult = await backendFetch(page, `/v1.0/m8flow/task-review/${taskId}`);
  expect(detailResult.status, `GET task #${taskId} detail`).toBe(200);
  const detail = detailResult.body as TaskDetail;
  const fields = detail.form?.schema?.properties ?? {};
  const outcomes = detail.outcomes ?? [];

  let button: Locator;
  let label: string;
  if (outcomes.length) {
    const wanted = typeof answer.outcome === 'string' ? answer.outcome.toLowerCase() : undefined;
    // A decision value from the gateway ("reject", "changes"), or the default flow, named after its flow ("Approve").
    const chosen = outcomes.find((o) => o.value.toLowerCase() === wanted || o.label.toLowerCase() === wanted) ?? outcomes.at(-1)!;
    label = chosen.label;
    button = page.getByRole('button', { name: chosen.label, exact: true });
  } else {
    label = 'Submit';
    button = page.getByRole('button', { name: /^(Submit|Continue)$/ });
  }

  await page.goto(`/task-review/${taskId}`);
  await expect(button).toBeVisible();
  for (const [key, value] of Object.entries(answer)) {
    if (key === 'outcome' || value === undefined) continue;
    const field = fields[key];
    if (!field) {
      const shown = Object.keys(fields);
      throw new Error(
        shown.length
          ? `task #${taskId}: the answer has "${key}", which is not a field on the form (fields: ${shown.join(', ')})`
          : `task #${taskId}: Task Review shows NO form fields for this task, so "${key}" cannot be entered (its form file was not loaded)`,
      );
    }
    await fillField(page, key, field, value);
  }
  // A submit that never gets an answer (the page then shows e.g. "Failed to fetch") fails here
  // with what the page says, instead of waiting until the whole test times out.
  const answered = page
    .waitForResponse((r) => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith(`/task-review/${taskId}/submit`), { timeout: 60_000 })
    .catch(async (error: unknown) => {
      const shown = await page.getByRole('alert').first().innerText({ timeout: 2_000 }).catch(() => '');
      const failed = await page.getByText('Failed to fetch').first().isVisible().catch(() => false);
      // The reason the wait ended (a 60 s timeout, or e.g. the page closing) and where the page is now.
      const reason = String(error instanceof Error ? error.message : error).split('\n')[0].slice(0, 200);
      throw new Error(
        `task #${taskId}: clicking "${label}" got no answer the test could see (${reason}); ` +
          `the page is at ${new URL(page.url()).pathname} and shows: ${shown || (failed ? 'Failed to fetch' : 'nothing')}`,
      );
    });
  const [response] = await Promise.all([answered, button.click()]);
  const text = await response.text();
  let body: Record<string, unknown> | null = null;
  try {
    body = JSON.parse(text) as Record<string, unknown>;
  } catch {
    body = null;
  }
  if (response.status() < 300) {
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    return { status: response.status(), body, button: label };
  }
  // A refused submit: the page shows why and stays on the task.
  const alert = page.getByRole('alert').first();
  await expect(alert).toBeVisible();
  return { status: response.status(), body, button: label, alert: (await alert.innerText()).trim() };
}

/** The submitter opens the seeded model page and clicks "Start process"; returns the instance id. */
async function startOnPage(page: Page, model: SeededModelCopy): Promise<number> {
  await page.goto(model.detailPath);
  await page.getByRole('button', { name: 'Start process', exact: true }).click();
  return waitForInstancePage(page);
}

type RunResult = {
  id: number;
  /** BPMN ids of the tasks submitted, in order. */
  worked: string[];
  /** Who submitted each, for the log. */
  by: string[];
  detail: InstanceDetail;
  /** Set when a submit was answered with automatic_step_failed (or the older service_task_error). */
  serviceError?: string;
  errorCode?: string;
  taskSubmitted?: boolean;
  failedTask?: string;
  stillOpen?: boolean;
};

/** Starts the seeded model and works its tasks as the path says, until the instance ends (or a submit fails, for service_error paths). */
async function runPath(browser: Browser, modelId: string, model: SeededModelCopy, path: CatalogPath): Promise<RunResult> {
  const ids = humanTaskIds(modelId);
  const answers = Object.fromEntries(Object.entries(path.answers).map(([k, v]) => [k, Array.isArray(v) ? [...v] : v]));
  const leave = new Set(path.leave ?? []);
  const wantError = path.expect === 'service_error';
  const id = await withPage(browser, submitterCredentials(), (page) => startOnPage(page, model));
  started.push(id);
  test.info().annotations.push({ type: 'instance', description: `#${id} of ${model.route}` });
  const worked: string[] = [];
  const by: string[] = [];
  const deadline = Date.now() + 150_000;
  while (Date.now() < deadline) {
    const detail = await withPage(browser, editorCredentials(), (page) => instanceDetail(page, id));
    if (detail.status === 'complete') {
      if (wantError) throw new Error(`instance #${id} completed, but a connector call should have failed (worked: ${worked.join(', ')})`);
      return { id, worked, by, detail };
    }
    if (detail.status === 'error') {
      throw new Error(`instance #${id} went into error after ${worked.join(', ') || 'no task'}: ${detail.error_message ?? ''}`);
    }
    let done = false;
    for (const persona of WORKERS) {
      const tasks = await withPage(browser, persona, async (page) => (await inbox(page)).filter((t) => t.process_instance_id === id));
      const task = tasks
        .map((t) => ({ t, bpmn: ids.get(t.task_name) ?? ids.get(taskTitle(t).replace(/ \[child\]$/, '')) ?? taskTitle(t) }))
        .find(({ bpmn }) => !leave.has(bpmn));
      if (!task) continue;
      const { t, bpmn } = task;
      const queued = answers[bpmn];
      if (queued === undefined) throw new Error(`instance #${id}: unexpected task "${taskTitle(t)}" (${bpmn}) for ${persona.username}; worked: ${worked.join(', ')}`);
      const answer = Array.isArray(queued) ? (queued.length > 1 ? queued.shift() : queued[0]) : queued;
      const result = await withPage(browser, persona, (page) => submitOnPage(page, t.id, answerValue(answer) as Record<string, unknown>));
      const errorCode = (result.body as { error_code?: string } | null)?.error_code;
      if (wantError && result.status >= 500 && (errorCode === 'automatic_step_failed' || errorCode === 'service_task_error')) {
        const after = await withPage(browser, editorCredentials(), (page) => instanceDetail(page, id));
        const stillOpen = await withPage(browser, persona, async (page) => (await inbox(page)).some((x) => x.id === t.id));
        const body = result.body as { message?: string; task_submitted?: boolean };
        return { id, worked, by, detail: after, serviceError: result.alert ?? body.message ?? errorCode, errorCode, taskSubmitted: body.task_submitted, failedTask: bpmn, stillOpen };
      }
      expect(result.status, `submit "${taskTitle(t)}" as ${persona.username} on the page (${result.button}): ${result.alert ?? JSON.stringify(result.body)}`).toBeLessThan(300);
      worked.push(bpmn);
      by.push(`${taskTitle(t)} (${persona.username}, ${result.button})`);
      done = true;
      break;
    }
    // Nothing to submit: a timer or the engine is still moving on.
    if (!done) await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(`instance #${id} of ${model.route} did not end within 2.5 minutes (worked: ${worked.join(', ') || 'none'})`);
}

/**
 * Data of the completed element `bpmnId`. An element can be listed more than
 * once (for example once as completed and once as a cancelled or future copy on
 * another branch), so the completed one is read, not simply the first.
 */
async function completedTaskData(page: Page, instanceId: number, bpmnId: string): Promise<Record<string, unknown>> {
  const detail = await instanceDetail(page, instanceId);
  const task = detail.tasks.find((t) => t.bpmn_identifier === bpmnId && /^completed$/i.test(t.state));
  if (!task) return taskData(page, instanceId, bpmnId);
  const reader = await withPage(page.context().browser()!, tenantAdminCredentials(), async (admin) => admin);
  const result = await backendFetch(reader, `/v1.0/m8flow/process-instances/${instanceId}/tasks/${encodeURIComponent(task.guid)}`);
  expect(result.status, `GET task data of ${bpmnId}`).toBe(200);
  return ((result.body as { data?: Record<string, unknown> }).data ?? {}) as Record<string, unknown>;
}

const reached = (detail: InstanceDetail, bpmnId: string) =>
  detail.tasks.some((t) => t.bpmn_identifier === bpmnId && /^completed$/i.test(t.state));

const MODELS = loadBaseline()
  .catalog.models.filter((m) => m.status === 'published')
  .map((m) => ({ id: m.id, name: m.name, paths: catalogPaths(m.id) }))
  .filter((m) => m.paths.length > 0);
const orderModel = seededModel('order-fulfilment');

test.describe('Seeded catalog: every route through every seeded process', () => {
  test.describe.configure({ timeout: 300_000 });

  /** Whether the tenant has the e2e postgres connector profile (see postgresConnection). */
  let postgres = true;

  test.beforeAll(async ({ browser }) => {
    // The seed signs in every test user once (about 1-1.5 min on a fresh stack).
    test.setTimeout(480_000);
    await seedBaselineOnce(browser);
    postgres = await withPage(browser, tenantAdminCredentials(), hasPostgresProfile);
  });

  test.afterAll(async ({ browser }) => {
    // Tenant admin: since M8F-627 only the starter or a tenant admin may delete an instance.
    await withPage(browser, tenantAdminCredentials(), (page) => deleteInstanceIds(page, started.splice(0)));
    await closeRolePages();
  });

  for (const m of MODELS) {
    const model = seededModel(m.id);
    for (const path of m.paths) {
      test(`${path.id}: ${path.title}`, async ({ browser }) => {
        const connection = postgresConnection();
        test.skip(
          usesPostgres(m.id) && !postgres,
          `No postgres connector profile: ${connection.dsn === null ? connection.reason : 'it could not be created'}. Set M8FLOW_E2E_PG_DSN to run this route.`,
        );
        const run = await runPath(browser, m.id, model, path);
        const sortedEqual = (a: string[], b: string[]) => expect([...a].sort()).toEqual([...b].sort());
        if (path.expect_tasks) sortedEqual(run.worked, path.expect_tasks);
        const checks: string[] = [];

        if (path.expect === 'service_error') {
          // Since the fix of the "unclear error" ticket: the task is saved, the answer says the next
          // automatic step failed (naming the connector), and the instance is in Error.
          expect(run.failedTask, 'the submit that reaches the failing connector call').toBe(path.failing_submit);
          expect(run.errorCode, 'error code of the answer').toBe('automatic_step_failed');
          expect(run.taskSubmitted, 'the answer says the task was submitted').toBe(true);
          expect(run.serviceError ?? '', 'the message explains it').toMatch(/next automatic step failed/i);
          expect(run.serviceError ?? '', 'the message names the connector').toMatch(/connector/i);
          expect(run.stillOpen, `${path.failing_submit} is no longer in Task Review`).toBe(false);
          await expect
            .poll(async () => (await withPage(browser, editorCredentials(), (page) => instanceDetail(page, run.id))).status, {
              message: `instance #${run.id} is in Error`,
              timeout: 20_000,
            })
            .toBe('error');
          checks.push(`submit of ${run.failedTask} answered: ${run.serviceError}`, `task saved: ${run.taskSubmitted}`, 'instance in Error');
        } else {
          for (const bpmnId of [...(path.expect_end ?? []), ...(path.expect_completed ?? [])]) {
            expect(reached(run.detail, bpmnId), `${bpmnId} reached`).toBe(true);
          }
          for (const bpmnId of path.expect_not_reached ?? []) {
            expect(reached(run.detail, bpmnId), `${bpmnId} not reached`).toBe(false);
          }
          checks.push(`reached ${[...(path.expect_end ?? []), ...(path.expect_completed ?? [])].join(', ') || '-'}`);
          if (path.expect_not_reached?.length) checks.push(`not reached ${path.expect_not_reached.join(', ')}`);
          if (path.expect_data) {
            const { at, values, absent } = path.expect_data;
            const data = await withPage(browser, editorCredentials(), (page) => completedTaskData(page, run.id, at));
            expect(data, `data at ${at}`).toMatchObject(values);
            for (const key of absent ?? []) expect(data, `${key} is not set on this path`).not.toHaveProperty(key);
            checks.push(`data at ${at}: ${JSON.stringify(values)}`);
          }
        }
        logResult(path.id, {
          scenario: `${path.title} (seeded model ${model.route})`,
          actions: ['Start as submitter', ...run.by.map((w) => `Submit ${w}`), ...(path.leave ?? []).map((l) => `Leave ${l} for its timer`)],
          expected: path.expect === 'service_error' ? 'The task is saved, the answer explains that the next automatic step (the connector call) failed, and the instance is in Error' : `Instance completes as listed in paths.json`,
          actual: `Instance #${run.id}: ${checks.join('; ')}`,
        });
      });
    }
  }

  test('ORD-04: Order Fulfilment: the sales order submitted from the Task Review page (as a person does)', async ({ browser }) => {
    test.skip(!postgres, 'No postgres connector profile (Order Fulfilment records the order in the database). Set M8FLOW_E2E_PG_DSN to run it.');
    // The API routes send only the form fields. The Task Review page pre-fills its
    // form with the process data and sends it all back; this test clicks through the
    // page like a person and records exactly what the page sent. Order Fulfilment
    // has a data object, which the data-object bug breaks (see the bug ticket).
    await withPage(browser, submitterCredentials(), async (sub) => {
      const id = await startMockInstance(sub, orderModel.route);
      started.push(id);
      test.info().annotations.push({ type: 'instance', description: `#${id} of ${orderModel.route}` });
      let task: TaskItem | undefined;
      await expect
        .poll(async () => {
          task = (await inbox(sub)).find((t) => t.process_instance_id === id && taskTitle(t) === 'Enter sales order');
          return Boolean(task);
        }, { message: 'task "Enter sales order" reaches the submitter', timeout: 30_000 })
        .toBe(true);

      await sub.goto(`/task-review/${task!.id}`);
      await expect(sub.getByRole('heading', { name: 'Enter sales order' })).toBeVisible();
      await sub.getByLabel(/^Customer/).fill('E2E from the page', { timeout: 20_000 });
      await sub.getByLabel(/^Items \(comma separated\)/).fill('laptop,mouse', { timeout: 20_000 });
      // Dispatch: today in the date picker (ships at once).
      await sub.getByLabel(/^Dispatch on/).fill(new Date().toISOString().slice(0, 10), { timeout: 20_000 });
      const [request, response] = await Promise.all([
        sub.waitForRequest((r) => r.method() === 'POST' && /\/task-review\/\d+\/submit$/.test(r.url())),
        sub.waitForResponse((r) => r.request().method() === 'POST' && /\/task-review\/\d+\/submit$/.test(r.url())),
        sub.getByRole('button', { name: 'Submit', exact: true }).click(),
      ]);
      const sent = (request.postDataJSON() ?? {}) as Record<string, unknown>;
      const shape = Object.entries(sent).map(([key, value]) => `${key}: ${Array.isArray(value) ? 'list' : value === null ? 'null' : typeof value}`);
      const answer = await response.text();
      test.info().annotations.push({ type: 'page sent', description: shape.join(', ') });
      console.log(`[ORD-04] the page sent: ${JSON.stringify(sent)}`);
      console.log(`[ORD-04] server answered ${response.status()}: ${answer}`);

      expect(response.status(), `submit from the page answered ${response.status()}: ${answer}; the page sent ${shape.join(', ')}`).toBeLessThan(300);
      await expect(sub).toHaveURL(urlPathEndsWith('/task-review'));
      logResult('ORD-04', {
        scenario: 'Order Fulfilment: Enter sales order submitted from the Task Review page',
        actions: ['Start as submitter', 'Open Enter sales order in Task Review', 'Fill customer, items and dispatch time', 'Click Submit'],
        expected: 'Submit succeeds and the page goes back to the Task Review list',
        actual: `Answered ${response.status()}; the page sent ${shape.join(', ')}`,
      });
    });
  });
});

test.describe('Seeded catalog: templates in place', () => {
  test.beforeAll(async ({ browser }) => {
    test.setTimeout(480_000);
    await seedBaselineOnce(browser);
  });

  test.afterAll(async () => {
    await closeRolePages();
  });

  test('SEED-02: Every catalog template is imported with exactly its files', async ({ browser }) => {
    const problems: string[] = [];
    const checked: string[] = [];
    await withPage(browser, editorCredentials(), async (page) => {
      for (const template of loadBaseline().catalog.templates ?? []) {
        const id = await seededTemplateId(page, template.key).catch((error: unknown) => {
          problems.push(String(error instanceof Error ? error.message : error));
          return undefined;
        });
        if (id === undefined) continue;
        const detail = await backendFetch(page, `/v1.0/m8flow/templates/${id}`);
        const files = templateFileNames(detail.body);
        const expected = Object.keys(templateFiles(template.key)).sort();
        if (detail.status !== 200) problems.push(`${templateKey(template.key)}: GET answered ${detail.status}`);
        else if (JSON.stringify(files) !== JSON.stringify(expected)) {
          problems.push(`${templateKey(template.key)}: files ${files.join(', ') || 'none'}, expected ${expected.join(', ')}`);
        }
        checked.push(template.key);
      }
    });
    expect(problems, 'templates missing or with other files than the catalog folder').toEqual([]);
    logResult('SEED-02', {
      scenario: 'The seeded catalog templates are in M8Flow (checked before the routes use them)',
      actions: ['Read every e2e-<key> template', 'Compare its files with seed/catalog/templates/<key>/'],
      expected: 'Every template is there with exactly the files of its catalog folder',
      actual: `${checked.length} template(s) checked: ${checked.join(', ')}`,
    });
  });
});

test.describe('Seeded catalog: a model kept paused', () => {
  test.beforeAll(async ({ browser }) => {
    test.setTimeout(480_000);
    await seedBaselineOnce(browser);
  });

  test.afterAll(async () => {
    await closeRolePages();
  });

  test('SEED-01: The seeded paused process is shown as Paused and cannot be started', async ({ browser }) => {
    const paused = seededModel('work-from-home-paused');
    const result = await withPage(browser, submitterCredentials(), async (sub) => {
      await sub.goto(paused.detailPath);
      const status = sub.getByTestId('process-model-status');
      await expect(status).toContainText('Paused');
      await expect(status).toContainText('Paused. Resume it to start new instances.');
      await expect(sub.getByRole('button', { name: 'Start process', exact: true })).toHaveCount(0);
      return startStatus(sub, paused.route);
    });
    expect(result, 'the server refuses to start a paused process').toBe(409);

    logResult('SEED-01', {
      scenario: `The seed keeps "${paused.name}" paused`,
      actions: ['Open the seeded paused process as submitter', 'Look for Start process', 'Start it through the API'],
      expected: 'Status Paused with its hint; no Start process button; the server refuses the start',
      actual: `Paused; no Start process button; start answered ${result}`,
    });
  });
});

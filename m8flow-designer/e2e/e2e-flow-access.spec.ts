import { readFileSync } from 'node:fs';

import { expect, test, type Browser, type Page } from '@playwright/test';

import {
  continueInTenant,
  editorCredentials,
  integratorCredentials,
  reviewerCredentials,
  signInAtSharedRealm,
  submitterCredentials,
  superAdminCredentials,
  tenantAdminCredentials,
  useSession,
  viewerCredentials,
  type DesignerPersona,
} from './helpers/auth';
import { addTenantMember, backendFetch, getSeededSecondTenant, removeTenantMember } from './helpers/backendApi';
import { PARITY_SECOND_TENANT_SLUG, SEED_TENANT_SLUG } from './helpers/fixtures';
import {
  createMockGroup,
  createMockModel,
  deleteMockGroup,
  removeMockModelCompletely,
  setModelStatus,
  setPrimaryFile,
} from './helpers/mockCatalog';
import {
  LANE,
  asOrgAdmin,
  completeTask,
  flowBpmn,
  homeStats,
  instanceDetail,
  processIdFor,
  startInstance,
  startStatus,
  statValue,
  tableRows,
  taskData,
  taskTitle,
  useFlowCatalog,
  waitForStatus,
  waitForTask,
  withPage,
  type FlowModel,
} from './helpers/processFlow';
import { logResult } from './helpers/processesPage';
import { seedProcessModelFile } from './helpers/seedFixture';
import { urlPathEndsWith } from './helpers/urls';

/**
 * Process flow: permissions, tenants and reliability.
 *
 * FLW-50  viewer and reviewer cannot start a process
 * FLW-51  tenant admin and editor can start the same process
 * FLW-52  a user signed in to another tenant cannot see the task or instance
 * FLW-53  switching tenant changes Task Review and Home counts
 * FLW-54  super admin sees the instance across tenants
 * FLW-55  refreshing the task page while filling the form
 * FLW-56  the flow cleanup leaves no test data
 *
 * FLW-52/53 add a seed user to the second test tenant and always remove it
 * again (same pattern as PAR-03).
 */

const APPROVAL_FORM = 'e2e-flow-review-schema.json';
const approvalForm = readFileSync(new URL(`./fixtures/e2e-flow/${APPROVAL_FORM}`, import.meta.url), 'utf-8');
const approve = { id: 'Activity_approve_request', name: 'E2E Approve Request', lane: LANE.approvers, form: APPROVAL_FORM };

const flow = useFlowCatalog(test, 'flowa', {
  approval: { name: 'E2E Access', bpmn: { steps: [approve] }, files: { [APPROVAL_FORM]: approvalForm } },
});

async function start(browser: Browser, persona: DesignerPersona = submitterCredentials(), model?: FlowModel): Promise<number> {
  return withPage(browser, persona, (p) => startInstance(p, flow, (model ?? flow.model('approval')).route));
}

async function instanceCount(browser: Browser): Promise<number> {
  // Tenant admin: the only role that lists every instance of the tenant (M8F-627).
  return withPage(browser, tenantAdminCredentials(), async (ed) => {
    const name = flow.model('approval').name;
    const result = await backendFetch(ed, `/v1.0/m8flow/process-instances?search=${encodeURIComponent(name)}&per_page=100`);
    return ((result.body as { results?: { process_model_display_name: string }[] }).results ?? []).filter(
      (r) => r.process_model_display_name === name,
    ).length;
  });
}

/** Signs in a user who belongs to two tenants and picks `slug` on the tenant page. */
async function signInToTenant(page: Page, persona: DesignerPersona, slug: string): Promise<void> {
  await signInAtSharedRealm(page, persona);
  expect(await continueInTenant(page, slug), 'a user in two tenants is asked to pick one').toBe(true);
}

/** Adds `username` to the second tenant for the duration of `action`, then removes it. */
async function inSecondTenant(
  browser: Browser,
  username: string,
  groups: string[],
  action: () => Promise<void>,
): Promise<void> {
  const tenantId = await withPage(
    browser,
    superAdminCredentials(),
    async (sa) => {
      // Seeded by the baseline (seed/seed.ts).
      const tenant = await getSeededSecondTenant(sa);
      await addTenantMember(sa, tenant.id, username, groups);
      return tenant.id;
    },
    'platformAdmin',
  );
  try {
    await action();
  } finally {
    await withPage(browser, superAdminCredentials(), (sa) => removeTenantMember(sa, tenantId, username), 'platformAdmin');
  }
}

test.describe('Process flow: permissions and tenants', { tag: ['@permissions'] }, () => {
  test('FLW-50: Viewer and reviewer cannot start a process', async ({ page, browser }) => {
    const m = flow.model('approval');
    const before = await instanceCount(browser);
    await useSession(page, viewerCredentials());
    await page.goto(`/processes/${m.route}`);
    await expect(page.getByRole('heading', { name: m.name, exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start process', exact: true })).toHaveCount(0);
    const viewer = await startStatus(page, m.route);
    const reviewer = await withPage(browser, reviewerCredentials(), (r) => startStatus(r, m.route));
    expect(viewer).toBe(403);
    expect(reviewer).toBe(403);
    expect(await instanceCount(browser)).toBe(before);

    logResult('FLW-50', {
      scenario: 'Start by roles without the start permission',
      actions: ['Viewer opens the published model', 'Viewer and reviewer call the start API'],
      expected: 'No "Start process" for the viewer; the API refuses both; no instance is created',
      actual: `No button; start API viewer ${viewer}, reviewer ${reviewer}; instances unchanged (${before})`,
    });
  });

  test('FLW-51: Tenant admin and editor can start the same process', async ({ browser }) => {
    const results: string[] = [];
    for (const [label, persona] of [
      ['tenant admin', tenantAdminCredentials()],
      ['editor', editorCredentials()],
    ] as const) {
      const id = await start(browser, persona);
      const startedBy = await withPage(browser, persona, async (p) => (await instanceDetail(p, id)).started_by);
      const task = await withPage(browser, reviewerCredentials(), (r) => completeTask(r, id, { approval_note: `Started by ${label}` }));
      // started_by is the username; "Submitted by" is the display name (e.g. "Editor M8Flow").
      expect(startedBy).toBe(persona.username);
      expect(task.submitted_by?.toLowerCase() ?? '').toContain(persona.username.toLowerCase());
      results.push(`${label}: #${id}, submitted by ${task.submitted_by}`);
    }

    logResult('FLW-51', {
      scenario: 'Authorized roles other than the submitter start the process',
      actions: ['Tenant admin starts', 'Editor starts', 'Reviewer completes both'],
      expected: 'Both starts work; each task shows the right "Submitted by"',
      actual: results.join('; '),
    });
  });

  test('FLW-52: A user signed in to another tenant cannot see the task or instance', async ({ browser }) => {
    test.setTimeout(180_000);
    const m = flow.model('approval');
    const id = await start(browser);
    const task = await withPage(browser, reviewerCredentials(), (r) => waitForTask(r, id));
    const integrator = integratorCredentials();
    const seen: Record<string, number | boolean> = {};

    await inSecondTenant(browser, integrator.username, ['Designers'], async () => {
      const context = await browser.newContext();
      const page = await context.newPage();
      try {
        await signInToTenant(page, integrator, PARITY_SECOND_TENANT_SLUG);
        const list = await backendFetch(page, `/v1.0/m8flow/process-instances?search=${encodeURIComponent(m.name)}`);
        seen.listed = ((list.body as { results?: { id: number }[] })?.results ?? []).some((r) => r.id === id);
        seen.instance = (await backendFetch(page, `/v1.0/m8flow/process-instances/${id}`)).status;
        seen.task = (await backendFetch(page, `/v1.0/m8flow/task-review/${task.id}`)).status;
        await page.goto('/process-instances');
        await page.getByRole('searchbox', { name: 'Search process instances' }).fill(m.name);
        await expect(tableRows(page, m.name)).toHaveCount(0);
      } finally {
        await context.close();
      }
    });
    expect(seen.listed).toBe(false);
    expect([403, 404]).toContain(seen.instance);
    expect([403, 404]).toContain(seen.task);

    logResult('FLW-52', {
      scenario: 'User of the second tenant and a m8flow instance',
      actions: ['Add integrator to the second tenant', 'Sign in and pick the second tenant', 'List, open and read the m8flow instance and task'],
      expected: 'Nothing from m8flow is listed; the instance and task are not found',
      actual: `Listed: ${seen.listed}; instance API ${seen.instance}; task API ${seen.task}`,
    });
  });

  test('FLW-53: Switching tenant changes Task Review and Home counts', async ({ browser }) => {
    test.setTimeout(240_000);
    // Own model: the reviewer may still have pending tasks of the shared model from other tests.
    const m = await flow.fresh(browser, 'approval');
    const id = await start(browser, submitterCredentials(), m);
    const task = await withPage(browser, reviewerCredentials(), (r) => waitForTask(r, id));
    const reviewer = reviewerCredentials();
    const counts: Record<string, string> = {};

    await inSecondTenant(browser, reviewer.username, ['Approvers'], async () => {
      for (const [label, slug, expectTask] of [
        ['second tenant', PARITY_SECOND_TENANT_SLUG, false],
        ['m8flow', SEED_TENANT_SLUG, true],
      ] as const) {
        const context = await browser.newContext();
        const page = await context.newPage();
        try {
          await signInToTenant(page, reviewer, slug);
          const stats = await homeStats(page);
          counts[label] = String(stats.tasks_waiting_on_me);
          await expect(statValue(page, 'Tasks waiting on me')).toHaveText(String(stats.tasks_waiting_on_me));
          await page.goto('/task-review');
          await expect(page.getByText('Loading…', { exact: true })).toHaveCount(0);
          await expect(tableRows(page, m.name)).toHaveCount(expectTask ? 1 : 0);
          if (expectTask) expect(stats.tasks_waiting_on_me ?? 0).toBeGreaterThanOrEqual(1);
        } finally {
          await context.close();
        }
      }
    });
    test.info().annotations.push({ type: 'setup', description: 'Needs the second tenant to have an "Approvers" group.' });

    logResult('FLW-53', {
      scenario: 'Reviewer in two tenants switches tenant',
      actions: ['Add reviewer to the second tenant (Approvers)', 'Sign in to the second tenant', 'Sign in to m8flow'],
      expected: 'The task and its count show only in m8flow',
      actual: `Task #${task.id}: second tenant waiting ${counts['second tenant']}, task not listed; m8flow waiting ${counts.m8flow}, task listed`,
    });
  });

  test('FLW-54: Super admin sees the instance across tenants', async ({ page, browser }) => {
    const m = await flow.fresh(browser, 'approval');
    const id = await start(browser, submitterCredentials(), m);
    await withPage(browser, reviewerCredentials(), (r) => completeTask(r, id, { approval_note: 'For super admin' }));
    await useSession(page, superAdminCredentials(), 'platformAdmin');
    const list = await backendFetch(page, `/v1.0/m8flow/process-instances?search=${encodeURIComponent(m.name)}&per_page=100`);
    expect(list.status).toBe(200);
    const row = ((list.body as { results: { id: number; tenant_name?: string | null; status: string }[] }).results ?? []).find((r) => r.id === id);
    expect(row, 'instance listed for super admin').toBeTruthy();
    expect(row!.tenant_name).toBeTruthy();
    await page.goto('/process-instances');
    await page.getByRole('searchbox', { name: 'Search process instances' }).fill(m.name);
    const uiRow = tableRows(page, m.name);
    await expect(uiRow).toHaveCount(1);
    await expect(uiRow).toContainText(row!.tenant_name!);
    const stats = await homeStats(page);
    expect(stats.total_tenants ?? 0).toBeGreaterThanOrEqual(1);

    logResult('FLW-54', {
      scenario: 'Super admin, All tenants view',
      actions: ['Complete a flow in m8flow', 'Login through Platform Admin Sign In', 'Open Process Instances and Home'],
      expected: 'The instance is listed with its tenant; Home shows Total tenants',
      actual: `Instance #${id} listed with tenant "${row!.tenant_name}" (${row!.status}); total tenants ${stats.total_tenants}`,
    });
  });
});

test.describe('Process flow: reliability', { tag: ['@reliability'] }, () => {
  test('FLW-55: Refreshing the task page while filling the form keeps the task pending', async ({ page, browser }) => {
    const id = await start(browser);
    await useSession(page, reviewerCredentials());
    const task = await waitForTask(page, id);
    await page.goto(`/task-review/${task.id}`);
    await expect(page.getByRole('heading', { level: 1, name: taskTitle(task), exact: true })).toBeVisible();
    const note = page.getByLabel('Approval note');
    await note.fill('Typed but not submitted');
    await page.reload();
    await expect(note).toHaveValue('');
    await note.fill('Submitted after refresh');
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    await expect(page).toHaveURL(urlPathEndsWith('/task-review'));
    const data = await withPage(browser, editorCredentials(), async (ed) => {
      await waitForStatus(ed, id, 'complete');
      return taskData(ed, id, approve.id);
    });
    expect(data.approval_note).toBe('Submitted after refresh');

    logResult('FLW-55', {
      scenario: 'Refresh before submitting',
      actions: ['Type a note', 'Refresh', 'Type another note and submit'],
      expected: 'Typed values are not saved by a refresh; the task stays pending and is completed once with the new value',
      actual: `After refresh the field was empty; saved "${data.approval_note}"`,
    });
  });

  test('FLW-56: The flow cleanup leaves no test data behind', async ({ page, browser }) => {
    await useSession(page, editorCredentials());
    const stamp = `${flow.stamp}c`;
    const groupId = `e2e-cleanup-${stamp}`;
    const modelId = `e2e-cleanup-model-${stamp}`;
    const route = `${groupId}:${modelId}`;
    await createMockGroup(page, { id: groupId, display_name: `E2E Cleanup ${stamp}` });
    await createMockModel(page, { group_id: groupId, id: modelId, display_name: `E2E Cleanup ${stamp}` });
    await seedProcessModelFile(page, APPROVAL_FORM, approvalForm, route);
    await seedProcessModelFile(
      page,
      'cleanup.bpmn',
      flowBpmn({ processId: processIdFor('flowa', 'cleanup', stamp), name: 'cleanup', steps: [approve] }),
      route,
    );
    await setPrimaryFile(page, route, 'cleanup.bpmn');
    await setModelStatus(page, route, 'published');
    const id = await withPage(browser, submitterCredentials(), (sub) => startInstance(sub, flow, route));
    await withPage(browser, reviewerCredentials(), (r) => completeTask(r, id, { approval_note: 'cleanup' }));
    await waitForStatus(page, id, 'complete');

    // The same cleanup the suite uses, as the tenant admin (the submitter
    // started the instance; since M8F-627 only it or a tenant admin may delete it).
    const left = await asOrgAdmin(browser, async (admin) => {
      await removeMockModelCompletely(admin, route);
      await deleteMockGroup(admin, groupId);
      return {
        instance: (await backendFetch(admin, `/v1.0/m8flow/process-instances/${id}`)).status,
        model: (await backendFetch(admin, `/v1.0/m8flow/process-models/${route}`)).status,
        // A single group cannot be read (405), so look for it in the group list.
        groupListed: ((await backendFetch(admin, '/v1.0/m8flow/process-groups')).body as { id: string }[]).some((g) => g.id === groupId),
      };
    });
    expect(left).toEqual({ instance: 404, model: 404, groupListed: false });

    logResult('FLW-56', {
      scenario: 'Create, run and clean up a flow',
      actions: ['Create group, model and instance', 'Run it to Complete', 'Run the cleanup helpers', 'Read the objects again'],
      expected: 'Instance and model are gone (404) and the group is no longer listed',
      actual: `instance ${left.instance}, model ${left.model}, group listed: ${left.groupListed}`,
    });
  });
});

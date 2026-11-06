import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Browser, Page } from '@playwright/test';

import {
  editorCredentials,
  integratorCredentials,
  reviewerCredentials,
  signInAsPlatformAdmin,
  signInAsSharedRealmUser,
  submitterCredentials,
  superAdminCredentials,
  tenantAdminCredentials,
  useSession,
  viewerCredentials,
  type DesignerPersona,
} from '../helpers/auth';
import {
  addTenantMember,
  assignTenantGroupMember,
  backendFetch,
  ensureKeycloakUser,
  ensureSecondParityTenant,
  ensureTenantGroup,
  cleanupLeftoverMockUsers,
  findTenantGroup,
  getSeedTenant,
  keycloakUserExists,
  type SeedUser,
} from '../helpers/backendApi';
import { TEST_TENANT_SLUG } from '../helpers/fixtures';
import { ensureMockProcessModel, sweepLeftoversOnce } from '../helpers/mockCatalog';

/**
 * E2E baseline seed (see baseline.json).
 *
 * Makes sure the fixed test data every run needs is in place, once per run:
 *   1. every test user signs in once and can open the app (on a new stack a
 *      user has no access until their first sign-in links them to the tenant);
 *   2. the platform admin signs in;
 *   3. the second tenant exists, with its own test users (editor, submitter,
 *      reviewer): each in a test group that carries that one role, signed in once;
 *   4. the shared mock process model exists, with its files.
 * Every step checks before it writes, so running it again changes nothing.
 * A step that fails is tried once more before the seed stops (see step()).
 *
 * It is called from the first test-data setup of a run (seedBaselineOnce),
 * so it runs locally, in the E2E gate and for any subset of specs. When it is
 * done it writes e2e/reports/<run id>/seed.json; later spec files and worker
 * restarts in the same run see that file and skip the seed.
 * A problem stops the run before the tests with a message naming the step.
 * No passwords or tokens are logged.
 */

type Baseline = {
  tenant: string;
  users: { role: string; groups?: string[] }[];
  platformAdmins: { role: string }[];
  secondTenant: { enabled: boolean; users?: { username: string; role: string; group: string }[] };
  mockModel: { enabled: boolean };
};

const PERSONAS: Record<string, () => DesignerPersona> = {
  editor: editorCredentials,
  submitter: submitterCredentials,
  reviewer: reviewerCredentials,
  tenantAdmin: tenantAdminCredentials,
  viewer: viewerCredentials,
  integrator: integratorCredentials,
  superAdmin: superAdminCredentials,
};

export function loadBaseline(): Baseline {
  return JSON.parse(readFileSync(new URL('./baseline.json', import.meta.url), 'utf-8')) as Baseline;
}

function persona(role: string): DesignerPersona {
  const make = PERSONAS[role];
  if (!make) throw new Error(`[seed] baseline.json: unknown role "${role}" (known: ${Object.keys(PERSONAS).join(', ')})`);
  return make();
}

/** Summary line, retry notices and errors: always shown. */
function log(message: string): void {
  console.log(`[seed] ${message}`);
}

/** Per-step detail: shown only with M8FLOW_E2E_SEED_VERBOSE=1 (the same detail is saved in seed.json). */
function detail(message: string): void {
  if (process.env.M8FLOW_E2E_SEED_VERBOSE === '1') console.log(`[seed] ${message}`);
}

const RETRY_WAIT_MS = 5_000;

/**
 * Runs one seed step in a fresh browser context. A step that fails is tried
 * once more after a short wait, in a new context: a one-off hiccup (for
 * example Keycloak showing its "sign-in form did not fully load" page) then
 * does not stop the run. Every step checks before it writes, so repeating it
 * is safe. If the second try fails too, its error stops the seed.
 */
async function step<T>(browser: Browser, label: string, action: (page: Page) => Promise<T>): Promise<T> {
  const once = async (): Promise<T> => {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      return await action(page);
    } finally {
      await context.close();
    }
  };
  try {
    return await once();
  } catch (error) {
    const reason = String(error).split('\n').at(0)?.slice(0, 300) ?? 'unknown error';
    console.warn(`[seed] ${label} failed, trying once more in ${RETRY_WAIT_MS / 1000} s: ${reason}`);
    await new Promise((resolve) => setTimeout(resolve, RETRY_WAIT_MS));
    const result = await once();
    log(`${label} worked on the second try`);
    return result;
  }
}

/**
 * Step 1: each test user signs in once and can open the app. The check is
 * GET /v1.0/onboarding, which every role may read; other pages differ by role
 * (the integrator, for example, may not read tasks), so they are not checked here.
 */
async function seedUsers(browser: Browser, baseline: Baseline): Promise<string[]> {
  const done: string[] = [];
  for (const { role } of baseline.users) {
    const user = persona(role);
    await step(browser, `sign-in of ${role} (${user.username})`, async (page) => {
      try {
        await signInAsSharedRealmUser(page, user, baseline.tenant);
      } catch (error) {
        throw new Error(
          `[seed] ${role} (${user.username}) cannot sign in to tenant "${baseline.tenant}". ` +
            `Is the user in the Keycloak realm import and a member of the tenant? ${String(error).slice(0, 300)}`,
        );
      }
      const result = await backendFetch(page, '/v1.0/onboarding');
      if (result.status !== 200) {
        throw new Error(
          `[seed] ${role} (${user.username}) signed in but GET /v1.0/onboarding answered ${result.status}: ` +
            'the user is not linked to the tenant yet.',
        );
      }
    });
    detail(`user ${role} (${user.username}) signed in and has access`);
    done.push(role);
  }
  return done;
}

/** Steps 2–3: the platform admin signs in; the second tenant exists. */
async function seedPlatform(browser: Browser, baseline: Baseline): Promise<string | undefined> {
  if (!baseline.platformAdmins.length && !baseline.secondTenant.enabled) return undefined;
  const admin = persona(baseline.platformAdmins.at(0)?.role ?? 'superAdmin');
  return step(browser, 'platform admin and second tenant', async (page) => {
    await signInAsPlatformAdmin(page, admin);
    detail(`platform admin (${admin.username}) signed in`);
    // Tenant the tests use: extra group memberships from baseline.json, and
    // leftover invited test users / invitations of stopped runs removed.
    // Test users come from the Keycloak realm import: check each one exists
    // before giving it a membership, and check the membership afterwards.
    const testTenant = await getSeedTenant(page);
    for (const { role, groups } of baseline.users) {
      if (!groups?.length) continue;
      const user = persona(role);
      if (!(await keycloakUserExists(page, user.username))) {
        throw new Error(
          `[seed] ${role} (${user.username}) does not exist in Keycloak, so it cannot be added to ${groups.join(', ')}. ` +
            'Test users come from the realm import: is the stack started with it?',
        );
      }
      await addTenantMember(page, testTenant.id, user.username, groups);
      for (const group of groups) {
        await assignTenantGroupMember(page, testTenant.id, group, user.username);
        await expectGroupMember(page, testTenant.id, group, user.username);
      }
      detail(`${role} (${user.username}) is in ${groups.join(', ')}`);
    }
    await cleanupLeftoverMockUsers(page, testTenant.id);
    if (!baseline.secondTenant.enabled) return undefined;
    const tenant = await ensureSecondParityTenant(page);
    detail(`second tenant "${tenant.slug}" is in place`);
    for (const user of baseline.secondTenant.users ?? []) {
      const groupCreated = await ensureTenantGroup(page, tenant.id, user.group, [user.role]);
      const userCreated = await ensureKeycloakUser(page, secondTenantUser(user.username, user.role));
      await addTenantMember(page, tenant.id, user.username, [user.group]);
      await assignTenantGroupMember(page, tenant.id, user.group, user.username);
      await expectGroupMember(page, tenant.id, user.group, user.username);
      detail(
        `second tenant: ${user.username} in group "${user.group}" (${user.role})` +
          `${userCreated ? ', user created' : ''}${groupCreated ? ', group created' : ''}`,
      );
    }
    return tenant.slug;
  });
}

/** Fails the seed when the tenant group does not list the user after it was added. */
async function expectGroupMember(page: Page, tenantId: string, group: string, username: string): Promise<void> {
  const row = await findTenantGroup(page, tenantId, group);
  if (!row?.members?.some((m) => m.username === username)) {
    throw new Error(`[seed] ${username} was added to group "${group}" but the group does not list them.`);
  }
}

/** The password of the second tenant's test users: the user name unless M8FLOW_E2E_TENANT2_PASSWORD is set. */
function secondTenantUser(username: string, role: string): SeedUser {
  return {
    username,
    password: process.env.M8FLOW_E2E_TENANT2_PASSWORD ?? username,
    email: `${username}@baseline.example.test`,
    firstName: 'E2E',
    lastName: `Tenant2 ${role}`,
  };
}

/** Step 3b: each second-tenant user signs in once (straight to that tenant) and can open the app. */
async function signInSecondTenantUsers(browser: Browser, baseline: Baseline, slug: string): Promise<string[]> {
  const done: string[] = [];
  for (const { username, role } of baseline.secondTenant.users ?? []) {
    const user = secondTenantUser(username, role);
    await step(browser, `sign-in of ${username} (second tenant)`, async (page) => {
      try {
        await signInAsSharedRealmUser(page, user, slug);
      } catch (error) {
        throw new Error(`[seed] ${username} cannot sign in to the second tenant "${slug}". ${String(error).slice(0, 300)}`);
      }
      const result = await backendFetch(page, '/v1.0/onboarding');
      if (result.status !== 200) {
        throw new Error(`[seed] ${username} signed in to "${slug}" but GET /v1.0/onboarding answered ${result.status}.`);
      }
    });
    detail(`second tenant: ${username} signed in and has access`);
    done.push(username);
  }
  return done;
}

/** Step 4: the shared mock model exists, with its files. */
async function seedCatalog(browser: Browser, baseline: Baseline): Promise<{ mockModel: boolean }> {
  return step(browser, 'leftover clean-up and shared mock model', async (page) => {
    await useSession(page, editorCredentials());
    await sweepLeftoversOnce(page);
    if (baseline.mockModel.enabled) {
      await ensureMockProcessModel(page);
      detail('shared mock model is in place');
    }
    return { mockModel: baseline.mockModel.enabled };
  });
}

function markerFile(): string | undefined {
  const runId = process.env.E2E_RUN_ID;
  return runId ? join('e2e', 'reports', runId, 'seed.json') : undefined;
}

/** Runs the whole seed now (also usable on its own, e.g. from a script). */
export async function seedBaseline(browser: Browser): Promise<void> {
  const baseline = loadBaseline();
  if (baseline.tenant !== TEST_TENANT_SLUG) {
    throw new Error(
      `[seed] baseline.json tenant "${baseline.tenant}" differs from the tenant the tests use ("${TEST_TENANT_SLUG}", M8FLOW_E2E_TENANT_SLUG).`,
    );
  }
  const started = Date.now();
  detail(`seeding the baseline for tenant "${baseline.tenant}"`);
  const secondTenant = await seedPlatform(browser, baseline);
  const users = await seedUsers(browser, baseline);
  const secondTenantUsers = secondTenant ? await signInSecondTenantUsers(browser, baseline, secondTenant) : [];
  const catalog = await seedCatalog(browser, baseline);
  const seconds = Math.round((Date.now() - started) / 100) / 10;
  const extras = [secondTenant ? 'second tenant' : '', catalog.mockModel ? 'mock model' : ''].filter(Boolean);
  log(`baseline ready in ${seconds} s (${users.length + secondTenantUsers.length} users${extras.map((e) => `, ${e}`).join('')})`);

  const file = markerFile();
  if (file) {
    try {
      mkdirSync(join(file, '..'), { recursive: true });
      writeFileSync(
        file,
        `${JSON.stringify({ at: new Date().toISOString(), seconds, tenant: baseline.tenant, users, secondTenant, secondTenantUsers, ...catalog }, null, 2)}\n`,
      );
    } catch {
      // The marker only saves repeating the seed in this run; a write problem is not a failure.
    }
  }
}

let seededInThisWorker = false;

function failedMarkerFile(): string | undefined {
  const file = markerFile();
  return file ? join(file, '..', 'seed-failed.json') : undefined;
}

/**
 * Seeds the baseline the first time a run needs it. Later calls in the same
 * worker, and in workers started after a failure (seed.json already written),
 * return at once.
 * If the seed fails, it writes seed-failed.json with the reason: every later
 * spec file in the run then stops at once with the same message instead of
 * trying the whole seed again.
 */
export async function seedBaselineOnce(browser: Browser): Promise<void> {
  if (seededInThisWorker) return;
  const file = markerFile();
  if (file && existsSync(file)) {
    seededInThisWorker = true;
    return;
  }
  const failed = failedMarkerFile();
  if (failed && existsSync(failed)) {
    const reason = (JSON.parse(readFileSync(failed, 'utf-8')) as { error?: string }).error ?? 'see the first failed spec';
    throw new Error(`[seed] the baseline seed failed earlier in this run; not repeating it. ${reason}`);
  }
  try {
    await seedBaseline(browser);
  } catch (error) {
    if (failed) {
      try {
        mkdirSync(join(failed, '..'), { recursive: true });
        writeFileSync(failed, `${JSON.stringify({ at: new Date().toISOString(), error: String(error).slice(0, 1000) }, null, 2)}\n`);
      } catch {
        // Without the marker the next spec simply tries again.
      }
    }
    throw error;
  }
  seededInThisWorker = true;
}

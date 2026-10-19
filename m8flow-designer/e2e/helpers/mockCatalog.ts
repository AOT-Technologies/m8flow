import { readFileSync } from 'node:fs';

import type { Browser, Page, TestType } from '@playwright/test';

import { editorCredentials, useSession } from './auth';
import { backendFetch } from './backendApi';
import {
  SEED_GROUP_ID,
  SEED_GROUP_NAME,
  SEED_MODEL_ID,
  SEED_MODEL_NAME,
  SEED_MODEL_ROUTE_ID,
  SEED_PRIMARY_FILE,
} from './fixtures';
import { seedProcessModelFile } from './seedFixture';

/**
 * Mock catalog data for the Processes and Modeler specs.
 *
 * Tests must not depend on, or change, the process groups/models that happen
 * to exist on an instance (it may have none, only groups, or groups with
 * models). Each spec creates the mock group/model it needs through the
 * backend API, works only on that, and deletes it afterwards.
 */

const MOCK_FILES = [
  SEED_PRIMARY_FILE,
  'wfh-form-schema.json',
  'wfh-review-form-schema.json',
  'wfh-form-uischema.json',
];

function mockFile(name: string): string {
  return readFileSync(new URL(`../fixtures/mock-model/${name}`, import.meta.url), 'utf-8');
}

function groupPath(groupId: string): string {
  return `/v1.0/m8flow/process-groups/${groupId.split('/').map(encodeURIComponent).join(':')}`;
}

function modelPath(routeId: string): string {
  return `/v1.0/m8flow/process-models/${routeId.split(':').map(encodeURIComponent).join(':')}`;
}

function ok(status: number, allowed: number[]): boolean {
  return (status >= 200 && status < 300) || allowed.includes(status);
}

export async function createMockGroup(
  page: Page,
  group: { id: string; display_name: string; description?: string },
): Promise<void> {
  const result = await backendFetch(page, '/v1.0/m8flow/process-groups', {
    method: 'POST',
    data: { description: 'E2E mock data -- safe to delete', ...group },
  });
  if (!ok(result.status, [409])) {
    throw new Error(`createMockGroup(${group.id}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

/** Creates a model and returns its route id (`group:model`). */
export async function createMockModel(
  page: Page,
  model: { group_id: string; id: string; display_name: string; description?: string },
): Promise<string> {
  const result = await backendFetch(page, '/v1.0/m8flow/process-models', {
    method: 'POST',
    data: { description: 'E2E mock data -- safe to delete', ...model },
  });
  if (!ok(result.status, [409])) {
    throw new Error(`createMockModel(${model.id}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
  return `${model.group_id.split('/').join(':')}:${model.id}`;
}

export async function setPrimaryFile(page: Page, routeId: string, fileName: string): Promise<void> {
  const result = await backendFetch(page, modelPath(routeId), {
    method: 'PUT',
    data: { primary_file_name: fileName },
  });
  if (!ok(result.status, [])) {
    throw new Error(`setPrimaryFile(${routeId}) failed: ${result.status} ${JSON.stringify(result.body)}`);
  }
}

/** Best effort: a cleanup problem is logged, never fails a test. */
export async function deleteMockModel(page: Page, routeId: string): Promise<void> {
  const result = await backendFetch(page, modelPath(routeId), { method: 'DELETE' }).catch(() => null);
  if (result && !ok(result.status, [404])) {
    console.warn(`[cleanup] delete mock model ${routeId} skipped: ${result.status}`);
  }
}

/** Best effort: a cleanup problem is logged, never fails a test. */
export async function deleteMockGroup(page: Page, groupId: string): Promise<void> {
  const result = await backendFetch(page, groupPath(groupId), { method: 'DELETE' }).catch(() => null);
  if (result && !ok(result.status, [404])) {
    console.warn(`[cleanup] delete mock group ${groupId} skipped: ${result.status}`);
  }
}

/**
 * The shared mock model the Modeler specs use (SEED_* in fixtures.ts):
 * group "E2E Mock Catalog" / model "E2E Mock Model" with a user-task BPMN
 * (primary) and mock form schema files. Re-uploading the files resets any
 * edit a previous run left behind.
 */
export async function ensureMockProcessModel(page: Page): Promise<void> {
  await createMockGroup(page, { id: SEED_GROUP_ID, display_name: SEED_GROUP_NAME });
  await createMockModel(page, { group_id: SEED_GROUP_ID, id: SEED_MODEL_ID, display_name: SEED_MODEL_NAME });
  for (const name of MOCK_FILES) {
    await seedProcessModelFile(page, name, mockFile(name), SEED_MODEL_ROUTE_ID);
  }
  await setPrimaryFile(page, SEED_MODEL_ROUTE_ID, SEED_PRIMARY_FILE);
}

export async function removeMockProcessModel(page: Page): Promise<void> {
  await deleteMockModel(page, SEED_MODEL_ROUTE_ID);
  await deleteMockGroup(page, SEED_GROUP_ID);
}

async function withEditorPage(browser: Browser, action: (page: Page) => Promise<void>): Promise<void> {
  const page = await browser.newPage();
  try {
    await useSession(page, editorCredentials());
    await action(page);
  } finally {
    await page.close();
  }
}

/**
 * Call once at the top of a spec file: creates the mock process model before
 * the file's tests and deletes it after them.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useMockProcessModel(test: TestType<any, any>): void {
  test.beforeAll(async ({ browser }) => {
    await withEditorPage(browser, ensureMockProcessModel);
  });
  test.afterAll(async ({ browser }) => {
    await withEditorPage(browser, removeMockProcessModel);
  });
}

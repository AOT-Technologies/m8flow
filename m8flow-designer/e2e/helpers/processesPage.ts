import { expect, type Locator, type Page, type Route } from '@playwright/test';

import { backendFetch } from './backendApi';

/**
 * Shared page helpers, API mocks and result logging for processes.spec.ts.
 */

export type ModelItem = {
  id: string;
  display_name: string;
  group_id: string;
  status?: string;
  tenant_name?: string | null;
};
export type GroupItem = { id: string; display_name: string };
export type OwnerOption = { id: number; username: string };

export const countLabel = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`;

export async function apiList<T>(page: Page, path: string): Promise<T[]> {
  const result = await backendFetch(page, path);
  expect(result.status, `GET ${path}`).toBe(200);
  return result.body as T[];
}

/** Model rows of the Processes table (each row has an "Open" button). */
export function modelRows(page: Page): Locator {
  return page
    .getByRole('table')
    .getByRole('button')
    .filter({ has: page.getByRole('button', { name: 'Open', exact: true }) });
}

export function modelRow(page: Page, name: string): Locator {
  return modelRows(page).filter({ hasText: name });
}

/** Display names of the listed rows, in the order shown. */
export async function listedModelNames(page: Page, candidates: string[]): Promise<string[]> {
  const texts = await modelRows(page).allInnerTexts();
  return texts
    .map((text) => candidates.find((name) => text.includes(name)))
    .filter((name): name is string => Boolean(name));
}

/** Opens a row's "More actions" menu and returns the menu. */
export async function openRowMenu(page: Page, name: string): Promise<Locator> {
  await modelRow(page, name).getByRole('button', { name: 'More actions', exact: true }).click();
  const menu = page.getByRole('menu');
  await expect(menu).toBeVisible();
  return menu;
}

/** Labels of the items in the open menu. */
export async function menuItemLabels(menu: Locator): Promise<string[]> {
  return (await menu.getByRole('menuitem').allInnerTexts()).map((t) => t.trim());
}

/** Picks an option of a "Label: value" pill dropdown (Status, Owner, Sort). */
export async function chooseDropdown(page: Page, label: string, option: string | RegExp): Promise<void> {
  await page.getByRole('button', { name: new RegExp(`^${label}: `) }).click();
  await page
    .getByRole('menuitemradio', typeof option === 'string' ? { name: option, exact: true } : { name: option })
    .click();
  await expect(page.getByRole('menu')).toHaveCount(0);
}

/** Visible text of every role="alert" on the page (UI error messages). */
export async function alertTexts(page: Page): Promise<string[]> {
  return (await page.getByRole('alert').allInnerTexts()).map((t) => t.trim()).filter(Boolean);
}

/** A file row in the model's Files section. */
export function fileRow(page: Page, fileName: string): Locator {
  return page
    .locator('#files div')
    .filter({ has: page.getByRole('link', { name: fileName, exact: true }) })
    .filter({ has: page.getByRole('button', { name: 'Download file' }) })
    .last();
}

export async function filesCount(page: Page): Promise<number> {
  const text = await page.getByRole('link', { name: /^Files \(\d+\)$/ }).innerText();
  return Number(/\((\d+)\)/.exec(text)?.[1] ?? NaN);
}

// ---------------------------------------------------------------------------
// API mocks (page.route). Browser calls go straight to the backend origin, so
// routes match on the URL path.
// ---------------------------------------------------------------------------

type Matcher = { method: string; path: string | RegExp };

function matches(route: Route, m: Matcher): boolean {
  const request = route.request();
  if (request.method() !== m.method) return false;
  const { pathname } = new URL(request.url());
  return typeof m.path === 'string' ? pathname === m.path : m.path.test(pathname);
}

/** Answers matching requests with `status` and a JSON body. Others pass through. */
export async function mockApi(page: Page, m: Matcher, status: number, body: unknown): Promise<void> {
  await page.route('**/v1.0/**', async (route) => {
    if (!matches(route, m)) {
      await route.fallback();
      return;
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

/**
 * New tenant with no data: the process model list, process group list and
 * owner list come back empty. Writes (POST/PUT/DELETE) still reach the backend.
 */
export async function mockEmptyCatalog(page: Page): Promise<void> {
  await mockApi(page, { method: 'GET', path: '/v1.0/m8flow/process-models' }, 200, []);
  await mockApi(page, { method: 'GET', path: '/v1.0/m8flow/process-groups' }, 200, []);
  await mockApi(
    page,
    { method: 'GET', path: '/v1.0/m8flow/process-instances/owners' },
    200,
    { owners: [], owner_options: [] },
  );
}

// ---------------------------------------------------------------------------
// Result log: printed once at the end of a test, so it only appears when
// every check above it passed.
// ---------------------------------------------------------------------------

export type TestLog = {
  scenario: string;
  actions: string[];
  expected: string;
  actual: string;
  messages?: string[];
};

export function logResult(id: string, log: TestLog): void {
  const lines = [
    `[${id}] PASSED - ${log.scenario}`,
    `  Actions:  ${log.actions.join(' -> ')}`,
    `  Expected: ${log.expected}`,
    `  Actual:   ${log.actual}`,
  ];
  if (log.messages?.length) {
    lines.push(`  UI messages: ${log.messages.map((m) => `"${m}"`).join(' | ')}`);
  }
  console.log(lines.join('\n'));
}

// ---------------------------------------------------------------------------
// UI text of the Processes page and its dialogs (checked as written in the app).
// ---------------------------------------------------------------------------

export const GROUP_PICKER_HINT = 'Pick a group to filter the model list, or manage groups here.';
export const GROUP_CREATE_HINT = 'The id is generated from the display name. Edit it to nest with parent/child.';
export const GROUP_EDIT_HINT = 'Display name and description only — the id does not change.';
export const GROUP_DELETE_HINT = 'Models in this group are removed from the catalog if none have instances.';
export const MODEL_FORM_INTRO = 'Creates a model under a process group and a default BPMN you can open in the modeler.';
export const MODEL_ID_HELP = 'Generated from the display name. You can edit it before creating.';

/** Toolbar of the Processes page: Showing pill, search, Status / Owner / Sort and the model count. */
export async function expectProcessesToolbar(page: Page, opts: { scope: string; models: number }): Promise<void> {
  await expect(page.getByText('Showing', { exact: true })).toBeVisible();
  // The Showing pill is the first button with the scope name (model rows repeat the group name).
  await expect(page.getByRole('button', { name: opts.scope, exact: true }).first()).toBeVisible();
  const search = page.getByRole('searchbox', { name: 'Search process models' });
  await expect(search).toBeEditable();
  await expect(search).toHaveAttribute('placeholder', 'Search process models');
  for (const name of ['Status: All', 'Owner: All', 'Sort: Newest first']) {
    await expect(page.getByRole('button', { name, exact: true })).toBeEnabled();
  }
  await expect(page.getByText(countLabel(opts.models, 'model'), { exact: true }).first()).toBeVisible();
}

/** Labels, placeholders and buttons of the New / Edit process group form. */
export async function expectGroupForm(dialog: Locator, mode: 'create' | 'edit'): Promise<void> {
  await expect(dialog.getByText(mode === 'create' ? GROUP_CREATE_HINT : GROUP_EDIT_HINT)).toBeVisible();
  for (const label of ['Display name', 'Id', 'Description']) {
    await expect(dialog.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(dialog.getByLabel('Process group display name')).toHaveAttribute('placeholder', 'Finance');
  const id = dialog.getByLabel('Process group id');
  await expect(id).toHaveAttribute('placeholder', 'Generated from the display name');
  if (mode === 'create') await expect(id).toBeEditable();
  else await expect(id).toBeDisabled();
  await expect(dialog.getByLabel('Process group description')).toHaveAttribute('placeholder', 'Optional');
  await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled();
  await expect(dialog.getByRole('button', { name: 'Close', exact: true })).toBeEnabled();
}

/** Labels, placeholders and help text of the New process model form. */
export async function expectModelForm(dialog: Locator): Promise<void> {
  await expect(dialog.getByText(MODEL_FORM_INTRO)).toBeVisible();
  for (const label of ['Process group', 'Display name', 'Identifier', 'Description (optional)']) {
    await expect(dialog.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(dialog.getByLabel('Display name')).toHaveAttribute('placeholder', 'Invoice Approval');
  await expect(dialog.getByLabel('Identifier')).toHaveAttribute('placeholder', 'invoice-approval');
  await expect(dialog.getByText(MODEL_ID_HELP)).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled();
}

/** True when the browser blocks the form because a required field is empty. */
export async function isValueMissing(field: Locator): Promise<boolean> {
  return field.evaluate((el) => (el as HTMLInputElement).validity.valueMissing);
}

/** A string of exactly `length` characters that starts with `prefix`. */
export function nameOfLength(prefix: string, length: number): string {
  return (prefix + 'x'.repeat(Math.max(0, length - prefix.length))).slice(0, length);
}

/** Same id rule as the app: lower case, spaces to "-", keep a-z 0-9 _ -, no repeated or edge "-"/"_". */
export function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9_-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^[-_]+|[-_]+$/g, '');
}

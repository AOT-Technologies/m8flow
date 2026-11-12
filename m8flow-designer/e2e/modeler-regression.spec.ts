import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useSeededModelCopy } from './helpers/seedCatalog';
import { openPropertiesPanelGroup, selectElement } from './helpers/diagram';
import { SEED_USER_TASK_ELEMENT_ID, SEED_USER_TASK_NAME } from './helpers/fixtures';

// Works on its own copy of the seeded "E2E Work From Home Request" model (deleted after the tests).
const model = useSeededModelCopy(test, 'modeler-panel', 'work-from-home');
// Works on its own copy of the seeded "E2E Invoice Approval" model (its "Calculate totals" script task).
const scriptModel = useSeededModelCopy(test, 'modeler-script', 'invoice-approval');

/**
 * CHK-11.. — Phase 0 baseline (see the phased Task Configuration Parity
 * plan). Locks in BpmnCanvas's current "Launch Editor" behavior *before*
 * later phases add more `spiff.*.requested`/`.edit` listeners next to it —
 * these two editors (Instructions/markdown, Pre-Script) are the only ones
 * BpmnCanvas answers today, and every later phase's spec file assumes this
 * one keeps passing. None of these tests click the top-level Save button —
 * they only exercise in-memory business-object edits on this spec's own copy
 * of the seeded model.
 */
test.describe('Process Modeler: task settings panel', () => {
  test('CHK-11: The Instructions editor opens, and edited text is saved to the task', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath());
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
    console.log('[CHK-11] Instructions editor saved the text to the user task.');
  });

  test('CHK-12: The Pre-Script editor opens with the correct title', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath());
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
    console.log('[CHK-12] Pre-Script editor opened with the correct title.');
  });

  test('CHK-13: Zoom buttons and the show/hide settings panel button work', async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath());
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    await page.getByTitle('Zoom in').click();
    await page.getByTitle('Zoom out').click();
    await page.getByTitle('Fit to viewport').click();

    await page.getByTitle('Hide properties panel').click();
    await expect(page.getByTitle('Show properties panel')).toBeVisible();
    await page.getByTitle('Show properties panel').click();
    await expect(page.getByTitle('Hide properties panel')).toBeVisible();
    console.log('[CHK-13] Zoom buttons and the show/hide settings panel button work.');
  });

  test('A user task has Guest options, and ticking one marks the diagram as changed', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    await page.goto(model.modelerPath());
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
    const guestGroup = await openPropertiesPanelGroup(page, 'allow_guest_user');
    await guestGroup.getByLabel('Guest can complete this task').check();
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
    console.log('Guest option is available on a user task and marks the diagram as changed.');
  });
});

const SCRIPT_TASK_ID = 'calculate_totals';

test.describe('Process Modeler: script tests', () => {
  test.beforeEach(async ({ page }) => {
    await useSession(page, editorCredentials());
    await page.goto(scriptModel.modelerPath());
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, SCRIPT_TASK_ID);
  });

  test('A script task test can be created and run from the script editor', async ({
    page,
  }) => {
    const group = await openPropertiesPanelGroup(page, 'spiff_script');
    await group.getByRole('button', { name: 'Launch Editor' }).click();

    const dialog = page.getByRole('dialog', { name: 'Edit Script — Calculate totals' });
    await expect(dialog).toBeVisible();
    await dialog.locator('.monaco-editor').click();
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
    await page.keyboard.type('x = 2');
    await dialog.getByRole('tab', { name: 'Unit tests' }).click();
    await dialog.getByRole('button', { name: 'Create unit test' }).click();
    await dialog.getByLabel('Expected output JSON').fill('{"x": 2}');
    await dialog.getByRole('button', { name: 'Run' }).click();
    await expect(dialog.getByRole('status')).toHaveText('Passed.');
    console.log('Script task test was created and passed.');
  });
});


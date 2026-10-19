import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  useSession,
} from './helpers/auth';
import { useMockProcessModel } from './helpers/mockCatalog';
import { dragShape } from './helpers/diagram';
import {
  SEED_MODEL_DETAIL_PATH,
  SEED_MODEL_NAME,
  SEED_MODELER_PATH,
  SEED_PRIMARY_FILE,
  seedModelerPath,
} from './helpers/fixtures';
import { deleteProcessModelFile, seedProcessModelFile } from './helpers/seedFixture';

/** A real task in the seed diagram, stable across runs (not a synthesized id). */
const DRAG_TARGET_ELEMENT_ID = 'Activity_submit_wfh';

async function gotoModeler(page: import('@playwright/test').Page) {
  await page.goto(SEED_MODELER_PATH);
  // Readiness gate, not a hard wait: dirty-tracking only attaches once
  // BpmnCanvas's importXML() resolves and the pill flips to Saved.
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  await expect(page.locator('.djs-container')).toBeVisible();
}

// Creates the mock process model before these tests and deletes it after.
useMockProcessModel(test);

/**
 * CHK-06..09 — Process Modeler journeys through the live designer → backend
 * seam, against the real seeded wfh-approval.bpmn diagram. See
 * .e2e-agent/research.md for the fixture and .e2e-agent/cases.md for the
 * CHK-08 round-trip rationale (Save is a real, persisting PUT).
 */
test.describe('m8flow-designer Process Modeler', () => {
  test('CHK-06: Open in modeler opens the primary file in a real, editable canvas', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    await page.goto(SEED_MODEL_DETAIL_PATH);
    await expect(page.getByRole('heading', { name: SEED_MODEL_NAME, exact: true })).toBeVisible();

    await page.getByRole('link', { name: 'Open in modeler' }).click();

    await expect(page).toHaveURL(new RegExp(`modeler/${SEED_PRIMARY_FILE}`));
    await expect(page.locator('header')).toContainText(SEED_PRIMARY_FILE);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await expect(page.locator('.djs-container')).toBeVisible();
    // A real diagram, not an empty canvas — the seeded task is rendered.
    await expect(page.locator(`[data-element-id="${DRAG_TARGET_ELEMENT_ID}"]`)).toBeVisible();
    console.log('[CHK-06] Open in modeler loaded the primary BPMN file in an editable canvas.');
  });

  test('CHK-07: modeler reports not-found for an unknown file name on a real model', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());

    await page.goto(SEED_MODELER_PATH.replace(SEED_PRIMARY_FILE, 'does-not-exist.bpmn'));

    await expect(page.getByText('File not found.', { exact: true })).toBeVisible();
    await expect(page.locator('.djs-container')).toHaveCount(0);
    console.log('[CHK-07] Unknown file shows "File not found." in the modeler.');
  });

  test('CHK-08: editing goes dirty, Save persists, and reload reflects the change', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    await gotoModeler(page);

    const target = page.locator(`[data-element-id="${DRAG_TARGET_ELEMENT_ID}"]`);
    const originalBox = await target.boundingBox();
    expect(originalBox).not.toBeNull();

    // 1. Edit -> dirty: Save button replaces the Saved pill.
    await dragShape(page, target, 60, 40);
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
    await expect(page.getByText('Saved', { exact: true })).toHaveCount(0);

    // 2. Save -> pill returns to Saved.
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    // 3. Reload proves the PUT actually persisted (not just client state).
    await page.reload();
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    const movedBox = await target.boundingBox();
    expect(movedBox!.x).not.toBeCloseTo(originalBox!.x, 0);
    expect(movedBox!.y).not.toBeCloseTo(originalBox!.y, 0);

    // No restore step: the mock model is created per run and deleted in afterAll,
    // and a drag-back cannot land on the exact original pixel (bpmn-js snapping).
    console.log('[CHK-08] Diagram change was saved and kept after reload.');
  });

  test('CHK-09: Download produces the current diagram XML', async ({ page }) => {
    await useSession(page, editorCredentials());
    await gotoModeler(page);

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Download' }).click(),
    ]);

    expect(download.suggestedFilename()).toBe(SEED_PRIMARY_FILE);
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) {
      chunks.push(chunk as Buffer);
    }
    const content = Buffer.concat(chunks).toString('utf-8');
    expect(content).toContain('<?xml');
    expect(content).toContain('bpmn:definitions');
    expect(content).toContain(DRAG_TARGET_ELEMENT_ID);
    console.log('[CHK-09] Download produced the current diagram XML.');
  });

  test('View XML shows the current diagram', async ({ page }) => {
    await useSession(page, editorCredentials());
    await gotoModeler(page);

    await page.getByRole('button', { name: 'View XML' }).click();
    const dialog = page.getByRole('dialog', { name: 'View XML' });
    await expect(dialog).toBeVisible();
    // M8F-524: View XML is now an editable Monaco editor, not a read-only <pre>.
    // Monaco only renders visible lines, so check the top of the document.
    await expect(dialog.getByText(SEED_PRIMARY_FILE, { exact: true })).toBeVisible();
    const editor = dialog.locator('.monaco-editor');
    await expect(editor).toBeVisible();
    await expect(editor.locator('.view-lines')).toContainText('bpmn:definitions');
    // Footer button is "Cancel" for editors and "Close" for read-only users.
    await dialog.getByRole('button', { name: /^(Cancel|Close)$/ }).last().click();
    await expect(dialog).toHaveCount(0);
    console.log('View XML shows the current diagram.');
  });

  test('unsaved edits warn before leaving; Stay keeps the process modeler open', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    await gotoModeler(page);

    await dragShape(page, page.locator(`[data-element-id="${DRAG_TARGET_ELEMENT_ID}"]`), 40, 20);
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();

    await page.getByRole('link', { name: 'Process Groups' }).click();
    const dialog = page.getByRole('alertdialog', { name: 'Unsaved changes' });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Stay' }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`modeler/${SEED_PRIMARY_FILE}`));
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
    console.log('Unsaved changes warning shown; Stay kept the modeler open.');
  });

  test('New file opens markdown in the process modeler; Delete returns to overview', async ({
    page,
  }) => {
    await useSession(page, editorCredentials());
    await gotoModeler(page);

    const stamp = `${Date.now()}`;
    const stem = `e2e-notes-${stamp}`;
    await page.getByRole('button', { name: 'New file' }).click();
    const addDialog = page.getByRole('dialog', { name: 'Add file' });
    await addDialog.getByRole('combobox', { name: 'File type' }).click();
    await page.getByRole('option', { name: 'Markdown' }).click();
    await addDialog.getByLabel('File name').fill(stem);
    await addDialog.getByRole('button', { name: 'Add file' }).click();

    await expect(page).toHaveURL(new RegExp(`modeler/${stem}\\.md$`));
    await expect(page.locator('.djs-container')).toHaveCount(0);
    await expect(page.locator('.monaco-editor')).toBeVisible();

    await page.getByRole('button', { name: 'Delete' }).click();
    const deleteDialog = page.getByRole('alertdialog', { name: 'Delete file' });
    await expect(deleteDialog).toContainText(`${stem}.md`);
    await deleteDialog.getByRole('button', { name: 'Delete' }).click();
    await expect(page).toHaveURL(SEED_MODEL_DETAIL_PATH);
    console.log('New Markdown file opened in the text editor and was deleted.');
  });

  test('generic JSON opens in the text editor, not a BPMN canvas', async ({ page }) => {
    await useSession(page, editorCredentials());
    const fileName = `e2e-generic-${Date.now()}.json`;
    await seedProcessModelFile(page, fileName, '{"ok":true}');
    try {
      await page.goto(seedModelerPath(fileName));
      await expect(page.getByText('Saved', { exact: true })).toBeVisible();
      await expect(page.locator('.djs-container')).toHaveCount(0);
      await expect(page.locator('.monaco-editor')).toBeVisible();
      await expect(page.locator('.monaco-editor')).toContainText('"ok"');
    } finally {
      await deleteProcessModelFile(page, fileName);
    }
    console.log('Generic JSON file opened in the text editor, not a BPMN canvas.');
  });
});

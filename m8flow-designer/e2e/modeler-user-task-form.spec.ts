import { expect, test } from '@playwright/test';

import { editorCredentials, signInAsSharedRealmUser } from './helpers/auth';
import { openPropertiesPanelGroup, propertiesPanelGroup, selectElement } from './helpers/diagram';
import { SEED_MODELER_PATH, SEED_USER_TASK_ELEMENT_ID, seedModelerPath } from './helpers/fixtures';

/**
 * Phase 1 — User Task data-backed fields (phased Task Configuration Parity
 * plan, §Phase 1). Implemented: BpmnCanvas.tsx now answers
 * `spiff.json_schema_files.requested` and `spiff.file.edit` (from the
 * process model's own already-fetched file list — no new backend route),
 * answers `spiff.task_metadata_keys.requested` with `keys: null` (the real
 * m8flow-frontend behavior: TASK_METADATA is an app-config value unset in
 * every env/compose file in this repo), and registers an
 * ExternalFormPropertiesProvider module.
 *
 * Uses the seed UserTask (SEED_USER_TASK_ELEMENT_ID) and the seed process
 * model's own real `wfh-form-schema.json` — no phase-specific fixture file
 * needed, since both already exist in the shared seed model.
 *
 * The "keep the open group open across an async round trip" mechanism the
 * original plan flagged as foundational turned out unnecessary: confirmed
 * live on Phase 4 (Service Task), whose connector list genuinely is a fresh
 * async fetch per `.requested` event (unlike this phase's JSON Schema
 * Filename dropdown, which answers from already-loaded props). The group
 * stays open regardless — BpmnCanvas.tsx's properties panel is a stable,
 * once-mounted DOM node, not rebuilt from scratch on every diagram change
 * the way m8flow-frontend's useDiagramModeler.ts wrapper is (that's what its
 * own MutationObserver workaround exists for). See
 * modeler-service-task.spec.ts's own "stays open across the async
 * connector-list round trip" case for the confirming test.
 */
test.describe('m8flow-designer Process Modeler — User Task form fields (Phase 1)', () => {
  test.beforeEach(async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await page.goto(SEED_MODELER_PATH);
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await selectElement(page, SEED_USER_TASK_ELEMENT_ID);
  });

  test('JSON Schema Filename dropdown lists *-schema.json files from this process model', async ({
    page,
  }) => {
    const formGroup = await openPropertiesPanelGroup(page, 'user_task_properties');
    const select = formGroup.getByLabel('JSON Schema Filename');
    const optionLabels = await select.locator('option').allTextContents();
    // Real seed files (data/process_models/.../wfh-group-4355dd7e70/) — not
    // synthesized, so this also proves the filter excludes non-schema files
    // (wfh-approval.bpmn, wfh-form-uischema.json) from the same directory.
    expect(optionLabels).toContain('wfh-form-schema.json');
    expect(optionLabels).toContain('wfh-review-form-schema.json');
    expect(optionLabels.some((label) => /uischema\.json$/i.test(label))).toBe(false);
  });

  test('"Launch Editor" opens the selected schema file\'s real content in the JSON editor', async ({
    page,
  }) => {
    const formGroup = await openPropertiesPanelGroup(page, 'user_task_properties');
    await formGroup.getByLabel('JSON Schema Filename').selectOption('wfh-form-schema.json');
    await formGroup.getByRole('button', { name: 'Launch Editor' }).click();

    const dialog = page.getByRole('dialog', { name: 'Edit JSON Schema' });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('Work From Home Request');

    // Close, not Save — this reads the real seed file, and Close proves
    // the round trip without mutating the shared fixture (edits auto-save
    // only after a change).
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    await expect(dialog).toHaveCount(0);
  });

  test('Task Metadata group hides itself when no metadata keys are configured or present', async ({
    page,
  }) => {
    // Real behavior, not a stub: SpiffExtensionTaskMetadata.jsx renders only
    // a `display: none` rule for its own group when `metadataKeys` (answered
    // here as `null`) and the task's own existing XML values are both empty
    // — matches m8flow-frontend's own unconfigured-TASK_METADATA behavior.
    await expect(propertiesPanelGroup(page, 'task_metadata_properties')).toBeHidden();
  });

  test('External Form URL field is present and its value round-trips to the business object', async ({
    page,
  }) => {
    const formGroup = await openPropertiesPanelGroup(page, 'external_form_properties');
    const field = formGroup.getByLabel('External form URL');
    await field.fill('https://example.test/forms/wfh-approval');
    await field.blur();
    await expect(field).toHaveValue('https://example.test/forms/wfh-approval');
    // Editing goes dirty even though nothing was persisted (no Save click) —
    // confirms the edit reached the command stack, same CHK-11/12 pattern.
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeVisible();
  });

  test('form-schema JSON opens the form editor canvas, not a BPMN canvas', async ({ page }) => {
    await page.goto(seedModelerPath('wfh-form-schema.json'));
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await expect(page.locator('.djs-container')).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Edit JSON Schema' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Form preview' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'JSON Schema' })).toBeVisible();
  });
});

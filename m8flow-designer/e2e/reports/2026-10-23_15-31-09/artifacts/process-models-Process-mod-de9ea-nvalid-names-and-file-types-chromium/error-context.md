# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: process-models.spec.ts >> Process model page for a tenant with data >> PRC-38: Add file trims names, adds the right extension and refuses invalid names and file types
- Location: e2e\process-models.spec.ts:746:3

# Error details

```
Error: expect(locator).toHaveAttribute(expected) failed

Locator: getByRole('dialog', { name: 'Add file' }).getByLabel('File name')
Expected: "diagram.bpmn"
Timeout: 20000ms
Error: element(s) not found

Call log:
  - Expect "toHaveAttribute" with timeout 20000ms
  - waiting for getByRole('dialog', { name: 'Add file' }).getByLabel('File name')

```

```yaml
- complementary:
  - text: m8flow Tenant m8flow
  - navigation:
    - link "Home":
      - /url: /
    - link "Processes":
      - /url: /processes
    - link "Process Instances":
      - /url: /process-instances
    - link "Task Review":
      - /url: /task-review
    - link "Messages":
      - /url: /messages
    - link "MCP Connection":
      - /url: /mcp-connection
    - button "Setup" [expanded]
    - link "Configuration":
      - /url: /configuration/secrets
    - link "Connectors":
      - /url: /connectors
    - link "Templates":
      - /url: /templates
  - button "Profile"
  - button "Switch to dark theme"
  - button "Locale"
- main:
  - button "All processes"
  - heading "E2E Files mvkt0oolxjf" [level=1]
  - text: Draft Not published yet. Publish it to start instances.
  - link "Open in modeler":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-approval.bpmn
  - button "Publish"
  - button "More actions"
  - link "E2E Process Model mvkt0oolxjf":
    - /url: /processes?group=e2e-pm-mvkt0oolxjf
  - paragraph: E2E mock data -- safe to delete
  - text: Last run — Running now 0 Runs 30d 0 Median time — Errors 30d — Group
  - link "E2E Process Model mvkt0oolxjf":
    - /url: /processes?group=e2e-pm-mvkt0oolxjf
  - text: Identifier e2e-pm-mvkt0oolxjf/e2e-files-mvkt0oolxjf
  - link "Instances":
    - /url: "#instances"
  - link "Files (7)":
    - /url: "#files"
  - link "Tests":
    - /url: "#tests"
  - heading "Recent instances" [level=2]
  - link "View all 0":
    - /url: /process-instances?search=E2E%20Files%20mvkt0oolxjf
  - table:
    - row "ID Started by Start Duration Status":
      - columnheader "ID"
      - columnheader "Started by"
      - columnheader "Start"
      - columnheader "Duration"
      - columnheader "Status"
    - text: No instances yet.
  - heading "Files" [level=2]
  - paragraph: BPMN, form schema and UI schema
  - button "Add file"
  - text: BPMN
  - link "e2e-files-mvkt0oolxjf.bpmn":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/e2e-files-mvkt0oolxjf.bpmn
  - text: BPMN · 2 KB · updated 1m ago
  - link "Edit file":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/e2e-files-mvkt0oolxjf.bpmn
  - button "Download file"
  - button "Set as primary"
  - button "Delete file"
  - text: MD
  - link "e2e-notes-mvkt0oolxjf.md":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/e2e-notes-mvkt0oolxjf.md
  - text: Markdown · 0 B · updated 43s ago
  - link "Edit file":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/e2e-notes-mvkt0oolxjf.md
  - button "Download file"
  - button "Delete file"
  - text: TXT
  - link "e2e-upload-mvkt0oolxjf.txt":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/e2e-upload-mvkt0oolxjf.txt
  - text: TXT · 28 B · updated 46s ago
  - link "Edit file":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/e2e-upload-mvkt0oolxjf.txt
  - button "Download file"
  - button "Delete file"
  - text: BPMN
  - link "wfh-approval.bpmn":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-approval.bpmn
  - text: BPMN · 2 KB · updated 1m ago Primary
  - link "Edit file":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-approval.bpmn
  - button "Download file"
  - text: JSON
  - link "wfh-form-schema.json":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-form-schema.json
  - text: Form schema · 387 B · updated 1m ago
  - link "Edit file":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-form-schema.json
  - button "Download file"
  - button "Delete file"
  - text: JSON
  - link "wfh-form-uischema.json":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-form-uischema.json
  - text: UI schema · 44 B · updated 1m ago
  - link "Edit file":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-form-uischema.json
  - button "Download file"
  - button "Delete file"
  - text: JSON
  - link "wfh-review-form-schema.json":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-review-form-schema.json
  - text: Form schema · 323 B · updated 1m ago
  - link "Edit file":
    - /url: /processes/e2e-pm-mvkt0oolxjf:e2e-files-mvkt0oolxjf/modeler/wfh-review-form-schema.json
  - button "Download file"
  - button "Delete file"
  - heading "Tests" [level=2]
  - paragraph: BPMN unit tests (test_*.json) and script-task unit tests
  - button "Run BPMN tests" [disabled]
  - heading "Script unit tests" [level=3]
  - button "Create script unit test"
  - paragraph: No script unit tests yet.
```

# Test source

```ts
  672 |     await expect(page).toHaveURL(urlPathEndsWith(`/processes/${active.groupId}:${leaf}`));
  673 |     await expect(page.getByRole('heading', { name: `E2E Trimmed Copy ${stamp}`, exact: true })).toBeVisible();
  674 |     checks.push(`id with spaces: copy created as "${leaf}"`);
  675 | 
  676 |     logResult('PRC-36', {
  677 |       scenario: 'Copy dialog with empty, invalid and space-padded values',
  678 |       actions: ['Space-only id', 'Invalid ids', 'Valid id and name with spaces'],
  679 |       expected: 'Copy disabled for a space-only id; invalid ids refused; spaces around a valid id and name are removed',
  680 |       actual: checks.join('; '),
  681 |       messages: [message],
  682 |     });
  683 |   });
  684 | 
  685 |   test('PRC-37: Save as template enforces the name rules, the 100-character limit and unique names', async ({
  686 |     page,
  687 |   }) => {
  688 |     const longName = nameOfLength(`E2E Template Max ${stamp} `, 100);
  689 |     const openDialog = async () => {
  690 |       await page.goto(`/processes/${route(M.draft)}`);
  691 |       await page.getByRole('button', { name: 'More actions', exact: true }).click();
  692 |       await page.getByRole('menuitem', { name: 'Save as template', exact: true }).click();
  693 |       return page.getByRole('dialog', { name: 'Save as template' });
  694 |     };
  695 |     let dialog = await openDialog();
  696 |     const intro = "Creates a draft template from this process model's BPMN, DMN, form-schema, and markdown files.";
  697 |     await expect(dialog.getByText(intro)).toBeVisible();
  698 |     for (const label of ['Name', 'Description (optional)', 'Category (optional)', 'Visibility', 'Tags (comma-separated, optional)']) {
  699 |       await expect(dialog.getByText(label, { exact: true })).toBeVisible();
  700 |     }
  701 |     await expect(dialog.getByLabel('Tags (comma-separated, optional)')).toHaveAttribute('placeholder', 'finance, approval');
  702 |     const name = dialog.getByLabel('Name', { exact: true });
  703 |     const submit = dialog.getByRole('button', { name: 'Create template' });
  704 |     const checks: string[] = [];
  705 | 
  706 |     await name.fill('     ');
  707 |     await expect(submit).toBeDisabled();
  708 |     checks.push('space-only name: Create disabled');
  709 |     const noLetter = 'Name must include a letter or number.';
  710 |     for (const value of ['___', '- - -']) {
  711 |       await name.fill(value);
  712 |       await submit.click();
  713 |       await expect(dialog.getByRole('alert')).toHaveText(noLetter);
  714 |       checks.push(`"${value}": refused`);
  715 |     }
  716 |     // Typing stops at 100 characters (the field's limit).
  717 |     await name.fill('');
  718 |     await name.pressSequentially('x'.repeat(130));
  719 |     await expect(name).toHaveValue('x'.repeat(100));
  720 |     checks.push('130 characters typed: field keeps 100');
  721 | 
  722 |     await name.fill(longName);
  723 |     await submit.click();
  724 |     await expect(page).toHaveURL(/\/templates\/\d+/);
  725 |     const templateId = Number(/templates\/(\d+)/.exec(page.url())?.[1]);
  726 |     created.templates.push(templateId);
  727 |     checks.push(`100-character name: template ${templateId} created`);
  728 | 
  729 |     dialog = await openDialog();
  730 |     await dialog.getByLabel('Name', { exact: true }).fill(longName);
  731 |     await dialog.getByRole('button', { name: 'Create template' }).click();
  732 |     const duplicate = `A template named '${longName}' already exists. Please choose a different name.`;
  733 |     await expect(dialog.getByRole('alert')).toHaveText(duplicate);
  734 |     await expect(page).toHaveURL(urlPathEndsWith(`/processes/${route(M.draft)}`));
  735 |     checks.push('same name again: refused');
  736 | 
  737 |     logResult('PRC-37', {
  738 |       scenario: 'Save as template name rules',
  739 |       actions: ['Space-only name', 'Names without letters or numbers', '130 characters', '100-character name', 'Same name again'],
  740 |       expected: 'Space-only disables Create; names without a letter/number refused; field stops at 100; 100 characters accepted; duplicate refused',
  741 |       actual: checks.join('; '),
  742 |       messages: [intro, noLetter, 'A template named ... already exists. Please choose a different name.'],
  743 |     });
  744 |   });
  745 | 
  746 |   test('PRC-38: Add file trims names, adds the right extension and refuses invalid names and file types', async ({
  747 |     page,
  748 |   }) => {
  749 |     const trimmed = `e2e-trim-${stamp}`;
  750 |     const withSuffix = `e2e-suffix-${stamp}.bpmn`;
  751 |     await page.goto(`/processes/${route(M.files)}`);
  752 |     const openAdd = async () => {
  753 |       await expect(page.getByRole('dialog')).toHaveCount(0);
  754 |       await page.getByRole('button', { name: 'Add file', exact: true }).click();
  755 |       const dialog = page.getByRole('dialog', { name: 'Add file' });
  756 |       await expect(dialog.getByLabel('File name')).toHaveValue('');
  757 |       return dialog;
  758 |     };
  759 |     const chooseType = async (dialog: Locator, type: string) => {
  760 |       await dialog.getByRole('combobox', { name: 'File type' }).click();
  761 |       await page.getByRole('option', { name: type, exact: true }).click();
  762 |     };
  763 |     const checks: string[] = [];
  764 | 
  765 |     let dialog = await openAdd();
  766 |     await dialog.getByRole('combobox', { name: 'File type' }).click();
  767 |     for (const type of ['BPMN', 'DMN', 'JSON', 'Markdown', 'Upload']) {
  768 |       await expect(page.getByRole('option', { name: type, exact: true })).toBeVisible();
  769 |     }
  770 |     await page.keyboard.press('Escape');
  771 |     const fileName = dialog.getByLabel('File name');
> 772 |     await expect(fileName).toHaveAttribute('placeholder', 'diagram.bpmn');
      |                            ^ Error: expect(locator).toHaveAttribute(expected) failed
  773 |     await chooseType(dialog, 'Markdown');
  774 |     await expect(fileName).toHaveAttribute('placeholder', 'diagram.md');
  775 |     await chooseType(dialog, 'Upload');
  776 |     await expect(fileName).toHaveAttribute('placeholder', 'notes.txt');
  777 |     await expect(dialog.getByLabel('Upload file')).toBeVisible();
  778 |     checks.push('types and placeholders matched');
  779 | 
  780 |     await chooseType(dialog, 'BPMN');
  781 |     await fileName.fill('     ');
  782 |     await expect(dialog.getByRole('button', { name: 'Add file', exact: true })).toBeDisabled();
  783 |     checks.push('space-only name: Add disabled');
  784 | 
  785 |     // Names and types the server refuses.
  786 |     const refused: [string, string][] = [
  787 |       ['BPMN', 'bad/name'],
  788 |       ['JSON', 'process_model'],
  789 |     ];
  790 |     for (const [type, value] of refused) {
  791 |       await chooseType(dialog, type);
  792 |       await fileName.fill(value);
  793 |       await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
  794 |       // A reserved name may already be known to the page ("already exists") or refused by the server.
  795 |       await expect(dialog.getByRole('alert')).toHaveText(/failed: 400|A file with this name already exists\./);
  796 |       checks.push(`${type} "${value}": refused (${await dialog.getByRole('alert').innerText()})`);
  797 |     }
  798 |     await chooseType(dialog, 'Upload');
  799 |     await fileName.fill('');
  800 |     await dialog.getByLabel('Upload file').setInputFiles({
  801 |       name: `e2e-bad-${stamp}.exe`,
  802 |       mimeType: 'application/octet-stream',
  803 |       buffer: Buffer.from('not allowed'),
  804 |     });
  805 |     await expect(fileName).toHaveValue(`e2e-bad-${stamp}.exe`);
  806 |     await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
  807 |     await expect(dialog.getByRole('alert')).toContainText('failed: 400');
  808 |     const message = await dialog.getByRole('alert').innerText();
  809 |     checks.push('.exe upload: refused');
  810 |     await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  811 |     await expect(page.getByRole('dialog')).toHaveCount(0);
  812 | 
  813 |     // Spaces around the name are removed; an extension already typed is not added twice.
  814 |     dialog = await openAdd();
  815 |     await chooseType(dialog, 'Markdown');
  816 |     await dialog.getByLabel('File name').fill(`   ${trimmed}   `);
  817 |     await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
  818 |     await expect(page).toHaveURL(urlPathEndsWith(`/modeler/${trimmed}.md`));
  819 |     checks.push(`"   ${trimmed}   " saved as ${trimmed}.md`);
  820 | 
  821 |     await page.goto(`/processes/${route(M.files)}`);
  822 |     dialog = await openAdd();
  823 |     await dialog.getByLabel('File name').fill(withSuffix);
  824 |     await dialog.getByRole('button', { name: 'Add file', exact: true }).click();
  825 |     await expect(page).toHaveURL(urlPathEndsWith(`/modeler/${withSuffix}`));
  826 |     checks.push(`"${withSuffix}" saved without a second .bpmn`);
  827 | 
  828 |     logResult('PRC-38', {
  829 |       scenario: 'Add file names, types and extensions',
  830 |       actions: ['Check types and placeholders', 'Space-only name', 'Name with "/"', 'Reserved name', '.exe upload', 'Name with spaces', 'Name with extension'],
  831 |       expected: 'Space-only disables Add; invalid name, reserved name and .exe refused; spaces removed; extension not doubled',
  832 |       actual: checks.join('; '),
  833 |       messages: [message],
  834 |     });
  835 |   });
  836 | 
  837 |   test('PRC-39: Create script unit test refuses an empty task id and input that is not a JSON object', async ({
  838 |     page,
  839 |   }) => {
  840 |     await page.goto(`/processes/${route(M.files)}`);
  841 |     await page.locator('#tests').getByRole('button', { name: 'Create script unit test' }).click();
  842 |     const dialog = page.getByRole('dialog', { name: 'Create script unit test' });
  843 |     const task = dialog.getByLabel('Script task ID');
  844 |     const input = dialog.getByLabel('Input JSON');
  845 |     const expected = dialog.getByLabel('Expected output JSON');
  846 |     const create = dialog.getByRole('button', { name: 'Create', exact: true });
  847 |     await expect(task).toHaveAttribute('placeholder', 'Script_1');
  848 |     await expect(input).toHaveValue('{}');
  849 |     await expect(expected).toHaveValue('{}');
  850 |     await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled();
  851 |     const checks: string[] = [];
  852 | 
  853 |     await task.fill('     ');
  854 |     await expect(create).toBeDisabled();
  855 |     checks.push('space-only task id: Create disabled');
  856 | 
  857 |     await task.fill('Script_1');
  858 |     const cases: [Locator, string, string][] = [
  859 |       [input, '[1, 2]', 'Input JSON must be a JSON object'],
  860 |       [input, 'null', 'Input JSON must be a JSON object'],
  861 |       [input, '"text"', 'Input JSON must be a JSON object'],
  862 |       [expected, '{bad', 'Expected output JSON must be valid JSON'],
  863 |       [expected, '42', 'Expected output JSON must be a JSON object'],
  864 |     ];
  865 |     for (const [field, value, message] of cases) {
  866 |       await input.fill('{}');
  867 |       await expected.fill('{}');
  868 |       await field.fill(value);
  869 |       await create.click();
  870 |       await expect(dialog.getByRole('alert')).toHaveText(message);
  871 |       checks.push(`${value}: "${message}"`);
  872 |     }
```
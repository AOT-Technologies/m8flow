// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// Locks the toolbar's permission gating and slot order. Expectations are written out
// literally per scenario rather than derived from the component, so a change to a CASL
// verb, a *Available switch or the button order fails here.

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { AbilityBuilder, Ability } from '@casl/ability';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@spiffworkflow-frontend/components/ConfirmButton', () => ({
  default: (props: any) => (
    <button
      type="button"
      data-testid={props['data-testid']}
      onClick={props.onConfirmation}
    >
      {props.buttonLabel}
    </button>
  ),
}));

vi.mock('@spiffworkflow-frontend/components/ProcessInstanceRun', () => ({
  default: () => <span data-testid="process-instance-run" />,
}));

import DiagramEditorToolbar from './DiagramEditorToolbar';

const FILE_PATH = '/process-models/g:m/files/x.bpmn';
const MODEL_PATH = '/process-models/g:m';

const ALL_VERBS: [string, string][] = [
  ['PUT', FILE_PATH],
  ['GET', FILE_PATH],
  ['DELETE', FILE_PATH],
  ['PUT', MODEL_PATH],
];
const READ_ONLY: [string, string][] = [['GET', FILE_PATH]];

function abilityFor(rules: [string, string][]) {
  const { can, build } = new AbilityBuilder(Ability);
  rules.forEach(([verb, target]) => can(verb, target));
  return build();
}

const noop = () => {};

const BASE = {
  diagramType: 'bpmn',
  fileName: 'x.bpmn',
  isPrimaryFile: false,
  processModel: { id: 'g:m' } as any,
  canViewXml: true,
  targetUris: {
    processModelFileShowPath: FILE_PATH,
    processModelShowPath: MODEL_PATH,
  },
  onSave: noop,
  onDelete: noop,
  onSetPrimaryFile: noop,
  onDownload: noop,
  onViewXml: noop,
  referencesButton: <button type="button" data-testid="refs" />,
  activeUserElement: <span data-testid="active-users" />,
  onSetPrimaryFileAvailable: true,
};

const theme = createTheme();

function renderToolbar(rules: [string, string][], overrides: object = {}) {
  const props: any = { ...BASE, ...overrides, ability: abilityFor(rules) };
  const { container } = render(
    <ThemeProvider theme={theme}>
      <DiagramEditorToolbar {...props} />
    </ThemeProvider>,
  );
  return {
    container,
    // Rendered controls in DOM order.
    slots: Array.from(container.querySelectorAll('[data-testid]')).map((el) =>
      el.getAttribute('data-testid'),
    ),
  };
}

const SAVE = 'process-model-file-save-button';
const RUN = 'process-instance-run';
const DELETE = 'process-model-file-delete-button';
const PRIMARY = 'diagram-set-primary-file-button';
const DOWNLOAD = 'diagram-download-button';
const VIEW_XML = 'diagram-view-xml-button';

describe('DiagramEditorToolbar', () => {
  it('shows every control when all verbs are permitted', () => {
    expect(renderToolbar(ALL_VERBS).slots).toEqual([
      SAVE,
      RUN,
      DELETE,
      PRIMARY,
      DOWNLOAD,
      VIEW_XML,
      'refs',
      'active-users',
    ]);
  });

  it('drops write-gated controls for a GET-only user', () => {
    // No save/delete/set-primary; view-xml and co-editor presence both need PUT.
    expect(renderToolbar(READ_ONLY).slots).toEqual([RUN, DOWNLOAD, 'refs']);
  });

  it('honours the host switches used by template file views', () => {
    const { slots } = renderToolbar(ALL_VERBS, {
      onDeleteAvailable: false,
      onViewXmlAvailable: false,
      onSetPrimaryFileAvailable: false,
    });
    expect(slots).toEqual([SAVE, RUN, DOWNLOAD, 'refs', 'active-users']);
  });

  it('treats the switches as on when left undefined', () => {
    const { slots } = renderToolbar(ALL_VERBS, {
      onDeleteAvailable: undefined,
      onViewXmlAvailable: undefined,
    });
    expect(slots).toContain(DELETE);
    expect(slots).toContain(VIEW_XML);
  });

  it('hides delete for the primary file and for an unnamed file', () => {
    expect(renderToolbar(ALL_VERBS, { isPrimaryFile: true }).slots).not.toContain(
      DELETE,
    );
    expect(renderToolbar(ALL_VERBS, { fileName: undefined }).slots).not.toContain(
      DELETE,
    );
  });

  it('hides view-xml when there is no XML form to open', () => {
    expect(renderToolbar(ALL_VERBS, { canViewXml: false }).slots).not.toContain(
      VIEW_XML,
    );
  });

  it('omits optional slots the host did not supply', () => {
    const { slots } = renderToolbar(ALL_VERBS, {
      processModel: null,
      referencesButton: null,
      activeUserElement: undefined,
    });
    expect(slots).toEqual([SAVE, DELETE, PRIMARY, DOWNLOAD, VIEW_XML]);
  });

  it('renders nothing for a read-only diagram', () => {
    expect(renderToolbar(ALL_VERBS, { diagramType: 'readonly' }).container)
      .toBeEmptyDOMElement();
  });

  it('wires each control to its own callback', () => {
    const calls: string[] = [];
    const handlers = {
      onSave: () => calls.push('save'),
      onDelete: () => calls.push('delete'),
      onSetPrimaryFile: () => calls.push('set-primary'),
      onDownload: () => calls.push('download'),
      onViewXml: () => calls.push('view-xml'),
    };
    const { container } = renderToolbar(ALL_VERBS, handlers);
    [
      [SAVE, 'save'],
      [DELETE, 'delete'],
      [PRIMARY, 'set-primary'],
      [DOWNLOAD, 'download'],
      [VIEW_XML, 'view-xml'],
    ].forEach(([testId, expected]) => {
      const el = container.querySelector<HTMLElement>(
        `[data-testid="${testId}"]`,
      );
      expect(el, testId).not.toBeNull();
      el!.click();
      expect(calls.at(-1)).toBe(expected);
    });
    expect(calls).toHaveLength(5);
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ProcessModelDetail } from '@/lib/api';
import {
  fileKind,
  formatBytes,
  formatDuration,
  ProcessModelOverview,
} from './ProcessModelOverview';

const DETAIL: ProcessModelDetail = {
  id: 'finance/invoice-approval',
  display_name: 'Invoice Approval',
  description: 'Two-step',
  group_id: 'finance',
  group_display_name: 'Finance',
  last_run_in_seconds: 1_700_000_000,
  running_now: 1,
  runs_30d: 12,
  recent_instances: [
    {
      id: 1042,
      started_by: 'editor',
      start_in_seconds: 1_700_000_000,
      duration_seconds: 102,
      status: 'complete',
    },
  ],
  files: [
    {
      name: 'invoice-approval.bpmn',
      size_bytes: 24576,
      updated_at_in_seconds: 1_700_000_000,
      primary: true,
    },
    {
      name: 'invoice-form-schema.json',
      size_bytes: 3000,
      updated_at_in_seconds: 1_700_000_000,
      primary: false,
    },
  ],
};

function renderOverview(detail: ProcessModelDetail = DETAIL) {
  return render(
    <MemoryRouter>
      <ProcessModelOverview detail={detail} />
    </MemoryRouter>,
  );
}

describe('formatDuration / formatBytes / fileKind', () => {
  it('formats duration and bytes', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(12)).toBe('12s');
    expect(formatDuration(102)).toBe('1m 42s');
    expect(formatBytes(500)).toBe('500 B');
    expect(formatBytes(24576)).toBe('24 KB');
  });

  it('maps file extensions', () => {
    expect(fileKind('a.bpmn')).toEqual({ ext: 'BPMN', label: 'BPMN' });
    expect(fileKind('test_notes.json')).toEqual({ ext: 'JSON', label: 'BPMN test' });
    expect(fileKind('form-schema.json')).toEqual({ ext: 'JSON', label: 'Form schema' });
    expect(fileKind('form-uischema.json')).toEqual({ ext: 'JSON', label: 'UI schema' });
    expect(fileKind('notes.md')).toEqual({ ext: 'MD', label: 'Markdown' });
  });
});

describe('ProcessModelOverview', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders live identity, stats, instances, and files', () => {
    renderOverview();

    expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    expect(screen.getByText('Two-step')).toBeInTheDocument();
    expect(screen.getByText('finance/invoice-approval')).toBeInTheDocument();
    expect(screen.getByText('Running now')).toBeInTheDocument();
    expect(screen.getByText('Runs 30d')).toBeInTheDocument();
    expect(screen.getByText('View all 12')).toBeInTheDocument();
    expect(screen.getByText('1042')).toBeInTheDocument();
    expect(screen.getByText('editor')).toBeInTheDocument();
    expect(screen.getByText('invoice-approval.bpmn')).toBeInTheDocument();
    expect(screen.getByText('Primary')).toBeInTheDocument();
    const groupLinks = screen.getAllByRole('link', { name: /Finance/ });
    expect(groupLinks).toHaveLength(2);
    for (const link of groupLinks) {
      expect(link).toHaveAttribute('href', '/processes?group=finance');
    }
  });

  it('omits unpublished facts and shows placeholder stats', () => {
    renderOverview();

    expect(screen.queryByText('Published')).not.toBeInTheDocument();
    expect(screen.queryByText('Owner')).not.toBeInTheDocument();
    expect(screen.queryByText('Trigger')).not.toBeInTheDocument();
    expect(screen.queryByText('Success rate')).not.toBeInTheDocument();
    expect(screen.getByText('Median time')).toBeInTheDocument();
    expect(screen.getByText('Errors 30d')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(2);
  });

  it('keeps header and file-creation controls from navigating', async () => {
    // Radix's DropdownMenu (ActionMenu, ticket 07) doesn't open under a
    // plain fireEvent.click in jsdom — use @testing-library/user-event, per
    // the map's Notes.
    const user = userEvent.setup();
    renderOverview();

    expect(screen.getByRole('button', { name: 'Start process' })).toBeDisabled();
    expect(screen.getByRole('link', { name: /Open in modeler/ })).toHaveAttribute(
      'href',
      '/processes/finance:invoice-approval/modeler/invoice-approval.bpmn',
    );
    expect(screen.queryByRole('button', { name: 'Save as template' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Copy' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit identity' })).not.toBeInTheDocument();
    const more = screen.getByRole('button', { name: 'More actions' });
    expect(more).not.toBeDisabled();
    await user.click(more);
    expect(await screen.findByRole('menuitem', { name: 'Copy' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('menuitem', { name: 'Save as template' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.queryByRole('menuitem', { name: 'Edit identity' })).not.toBeInTheDocument();
    // Radix hides the rest of the page from the accessibility tree while
    // the menu is open — close it before asserting on other controls.
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Add file' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Run BPMN tests' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Create script unit test' })).toBeDisabled();
  });

  it('starts a process when onStart is provided', async () => {
    const onStart = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} onStart={onStart} />
      </MemoryRouter>,
    );
    const start = screen.getByRole('button', { name: 'Start process' });
    expect(start).not.toBeDisabled();
    fireEvent.click(start);
    await waitFor(() => {
      expect(onStart).toHaveBeenCalledTimes(1);
    });
  });

  it('shows the shared unstartable message when start fails with 422', async () => {
    const { ApiError } = await import('@/lib/api');
    const onStart = vi.fn().mockRejectedValue(new ApiError('/start', 422, 'POST'));
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} onStart={onStart} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Start process' }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/missing a start event/);
    });
  });

  it('packs supported files and creates a draft when onSaveAsTemplate is provided', async () => {
    const user = userEvent.setup();
    const onSaveAsTemplate = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (String(url).includes('/v1.0/m8flow/templates') && init?.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: async () => ({ id: 7 }),
          });
        }
        return Promise.resolve({
          ok: true,
          text: async () => '<bpmn/>',
        });
      }),
    );
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} onSaveAsTemplate={onSaveAsTemplate} />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: 'More actions' }));
    const saveAs = await screen.findByRole('menuitem', { name: 'Save as template' });
    expect(saveAs).not.toBeDisabled();
    await user.click(saveAs);
    fireEvent.click(screen.getByRole('button', { name: 'Create template' }));
    await waitFor(() => {
      expect(onSaveAsTemplate).toHaveBeenCalledWith(7);
    });
    const fileGets = vi
      .mocked(fetch)
      .mock.calls.filter(([url, init]) => String(url).includes('/files/') && (!init || !init.method || init.method === 'GET'));
    expect(fileGets.map(([url]) => String(url))).toEqual(
      expect.arrayContaining([
        expect.stringContaining('/process-models/finance:invoice-approval/files/invoice-approval.bpmn'),
        expect.stringContaining('/process-models/finance:invoice-approval/files/invoice-form-schema.json'),
      ]),
    );
    expect(fileGets).toHaveLength(2);
  });

  it('opens copy when onCopy is provided', async () => {
    const user = userEvent.setup();
    const onCopy = vi.fn().mockResolvedValue({ id: 'finance/invoice-approval-copy' });
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} canManage onCopy={onCopy} />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: 'More actions' }));
    const copy = await screen.findByRole('menuitem', { name: 'Copy' });
    expect(copy).not.toBeDisabled();
    await user.click(copy);
    fireEvent.click(screen.getByRole('button', { name: 'Copy process model' }));
    await waitFor(() => {
      expect(onCopy).toHaveBeenCalledWith({
        id: 'invoice-approval-copy',
        display_name: 'Invoice Approval (copy)',
      });
    });
  });

  it('runs BPMN tests when a test_*.json file is present', async () => {
    const onRunBpmnTests = vi.fn().mockResolvedValue({
      all_passed: true,
      passing: [{ passed: true, bpmn_file: 'invoice-approval.bpmn', test_case_identifier: 'happy_path' }],
      failing: [],
    });
    render(
      <MemoryRouter>
        <ProcessModelOverview
          detail={{
            ...DETAIL,
            files: [
              ...DETAIL.files,
              {
                name: 'test_invoice-approval.json',
                size_bytes: 40,
                updated_at_in_seconds: 1_700_000_000,
                primary: false,
              },
            ],
          }}
          canManage
          onRunBpmnTests={onRunBpmnTests}
        />
      </MemoryRouter>,
    );
    const run = screen.getByRole('button', { name: 'Run BPMN tests' });
    expect(run).not.toBeDisabled();
    fireEvent.click(run);
    await waitFor(() => {
      expect(onRunBpmnTests).toHaveBeenCalled();
    });
    expect(screen.getByText('All 1 test passed.')).toBeInTheDocument();
  });

  it('lets an editor add, set primary, and delete files', async () => {
    const onAdd = vi.fn().mockResolvedValue(undefined);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const onSetPrimary = vi.fn().mockResolvedValue(undefined);
    const files = [
      ...DETAIL.files,
      {
        name: 'extra.bpmn',
        size_bytes: 100,
        updated_at_in_seconds: 1_700_000_000,
        primary: false,
      },
    ];
    render(
      <MemoryRouter>
        <ProcessModelOverview
          detail={{ ...DETAIL, files }}
          canManage
          onAddFile={onAdd}
          onDeleteFile={onDelete}
          onSetPrimary={onSetPrimary}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: 'Add file' })).not.toBeDisabled();
    fireEvent.click(screen.getByTitle('Set as primary'));
    await waitFor(() => {
      expect(onSetPrimary).toHaveBeenCalledWith('extra.bpmn');
    });
    fireEvent.click(screen.getAllByTitle('Delete file')[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => {
      expect(onDelete).toHaveBeenCalledWith('invoice-form-schema.json');
    });
  });

  it('lets an editor edit display name and description', async () => {
    const user = userEvent.setup();
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <ProcessModelOverview detail={DETAIL} canManage onUpdateIdentity={onUpdate} />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: 'More actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Edit identity' }));
    fireEvent.change(screen.getByLabelText('Process model display name'), {
      target: { value: 'Invoices' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalledWith({
        display_name: 'Invoices',
        description: 'Two-step',
      });
    });
  });

  it('wires the recent-instances "View all" link and each row id to Process Instances (ticket 04 capstone)', () => {
    renderOverview();

    expect(screen.getByRole('link', { name: /View all/ })).toHaveAttribute(
      'href',
      '/process-instances?search=Invoice%20Approval',
    );
    expect(screen.getByRole('link', { name: '1042' })).toHaveAttribute(
      'href',
      '/process-instances/1042',
    );
  });

  it('wires each file row to its own modeler link and download', () => {
    renderOverview();

    const editLinks = screen.getAllByTitle('Edit file');
    expect(editLinks).toHaveLength(DETAIL.files.length);
    expect(editLinks[0]).toHaveAttribute(
      'href',
      '/processes/finance:invoice-approval/modeler/invoice-approval.bpmn',
    );
    expect(editLinks[1]).toHaveAttribute(
      'href',
      '/processes/finance:invoice-approval/modeler/invoice-form-schema.json',
    );

    const downloadButtons = screen.getAllByTitle('Download file');
    expect(downloadButtons).toHaveLength(DETAIL.files.length);
    for (const button of downloadButtons) {
      expect(button).not.toBeDisabled();
    }
  });

  it('shows empty copy when there are no instances or files', () => {
    renderOverview({
      ...DETAIL,
      recent_instances: [],
      files: [],
    });

    expect(screen.getByText('No instances yet.')).toBeInTheDocument();
    expect(screen.getByText('No files yet.')).toBeInTheDocument();
    expect(screen.getByText('Files (0)')).toBeInTheDocument();
  });

  it('keeps Open in modeler disabled when there is no primary file', () => {
    renderOverview({ ...DETAIL, files: [{ ...DETAIL.files[1], primary: false }] });

    expect(screen.getByRole('button', { name: /Open in modeler/ })).toBeDisabled();
    expect(screen.queryByRole('link', { name: /Open in modeler/ })).not.toBeInTheDocument();
  });
});

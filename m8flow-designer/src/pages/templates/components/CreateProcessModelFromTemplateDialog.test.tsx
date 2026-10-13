import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { CreateProcessModelFromTemplateDialog } from './CreateProcessModelFromTemplateDialog';
import type { Template } from '@/lib/templatesApi';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    fetchProcessGroups: vi.fn(),
    createProcessGroup: vi.fn(),
  };
});

vi.mock('@/lib/templatesApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/templatesApi')>('@/lib/templatesApi');
  return {
    ...actual,
    createProcessModelFromTemplate: vi.fn(),
  };
});

import { ApiError, createProcessGroup, fetchProcessGroups } from '@/lib/api';
import { createProcessModelFromTemplate } from '@/lib/templatesApi';

const TEMPLATE = {
  id: 5,
  name: 'Approval Workflow',
  version: 'V1',
  isPublished: true,
  description: null,
  templateKey: 'approval-workflow',
  tags: null,
  category: null,
  tenantId: 't1',
  visibility: 'TENANT',
  files: [],
  status: 'published',
  createdBy: 'admin',
  modifiedBy: 'admin',
  createdAt: new Date(1000).toISOString(),
  updatedAt: new Date(1000).toISOString(),
} as Template;

describe('CreateProcessModelFromTemplateDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchProcessGroups).mockResolvedValue([
      {
        id: 'finance',
        tenant_id: 't1',
        display_name: 'Finance',
        description: '',
        model_count: 1,
        last_run_at: null,
      },
    ]);
    vi.mocked(createProcessModelFromTemplate).mockResolvedValue({
      process_model: { id: 'finance/from-template' },
      template_info: {
        id: 1,
        process_model_identifier: 'finance/from-template',
        source_template_id: 5,
        source_template_key: 'approval-workflow',
        source_template_version: 'V1',
        source_template_name: 'Approval Workflow',
        m8f_tenant_id: 't1',
        created_by: 'root',
        created_at: new Date(1000).toISOString(),
        updated_at: new Date(1000).toISOString(),
      },
    });
  });

  it('blocks create when needsTenant (All Tenants super-admin)', async () => {
    render(
      <CreateProcessModelFromTemplateDialog
        template={TEMPLATE}
        open
        onClose={vi.fn()}
        scopedTenantId={null}
        needsTenant
        onCreated={vi.fn()}
      />,
    );

    expect(screen.getByTestId('create-from-template-tenant-alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).toBeDisabled();
    expect(fetchProcessGroups).not.toHaveBeenCalled();
  });

  it('sends m8f_tenant_id and tenantId query when a concrete tenant is selected', async () => {
    const onCreated = vi.fn();
    render(
      <CreateProcessModelFromTemplateDialog
        template={TEMPLATE}
        open
        onClose={vi.fn()}
        scopedTenantId="t1"
        needsTenant={false}
        onCreated={onCreated}
      />,
    );

    await waitFor(() => expect(screen.getByLabelText('Process group')).toHaveTextContent('Finance'));
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));

    await waitFor(() => {
      expect(createProcessModelFromTemplate).toHaveBeenCalledWith(5, {
        processGroupId: 'finance',
        processModelId: expect.any(String),
        displayName: 'Approval Workflow',
        description: undefined,
        tenantId: 't1',
      });
      expect(onCreated).toHaveBeenCalled();
    });
  });

  it('shows an identifier validation message on 409 instead of the raw API error', async () => {
    vi.mocked(createProcessModelFromTemplate).mockRejectedValueOnce(
      new ApiError('/v1.0/m8flow/templates/5/create-process-model', 409, 'POST', 'exists'),
    );
    const onCreated = vi.fn();
    render(
      <CreateProcessModelFromTemplateDialog
        template={TEMPLATE}
        open
        onClose={vi.fn()}
        scopedTenantId="t1"
        onCreated={onCreated}
      />,
    );
    await waitFor(() => expect(screen.getByLabelText('Process group')).toHaveTextContent('Finance'));
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('identifier “approval-workflow” already exists');
    expect(alert).not.toHaveTextContent('409');
    expect(screen.getByLabelText('Identifier')).toHaveAttribute('aria-invalid', 'true');
    expect(onCreated).not.toHaveBeenCalled();

    // Editing the identifier clears the error and a retry succeeds.
    fireEvent.change(screen.getByLabelText('Identifier'), { target: { value: 'approval-2' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
  });

  it('creates and selects a process group inline when none exist', async () => {
    vi.mocked(fetchProcessGroups).mockResolvedValueOnce([]);
    vi.mocked(createProcessGroup).mockResolvedValueOnce({
      id: 'operations',
      tenant_id: 't1',
      display_name: 'Operations',
      description: '',
      model_count: 0,
      last_run_at: null,
    });
    render(
      <CreateProcessModelFromTemplateDialog
        template={TEMPLATE}
        open
        onClose={vi.fn()}
        scopedTenantId="t1"
        onCreated={vi.fn()}
      />,
    );
    const nameInput = await screen.findByLabelText('New process group name');
    expect(screen.getByRole('button', { name: 'Create process model' })).toBeDisabled();
    fireEvent.change(nameInput, { target: { value: 'Operations' } });
    fireEvent.click(screen.getByRole('button', { name: 'New process group' }));

    await waitFor(() => expect(screen.getByLabelText('Process group')).toHaveTextContent('Operations'));
    expect(createProcessGroup).toHaveBeenCalledWith(
      { id: 'operations', display_name: 'Operations', description: '' },
      't1',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));
    await waitFor(() =>
      expect(createProcessModelFromTemplate).toHaveBeenCalledWith(
        5,
        expect.objectContaining({ processGroupId: 'operations' }),
      ),
    );
  });

  it('shows a 409 on inline group create, clears it on edit, and retries', async () => {
    vi.mocked(fetchProcessGroups).mockResolvedValueOnce([]);
    vi.mocked(createProcessGroup)
      .mockRejectedValueOnce(new ApiError('/v1.0/m8flow/process-groups', 409, 'POST', 'exists'))
      .mockResolvedValueOnce({
        id: 'ops-2',
        tenant_id: 't1',
        display_name: 'Ops 2',
        description: '',
        model_count: 0,
        last_run_at: null,
      });
    render(
      <CreateProcessModelFromTemplateDialog
        template={TEMPLATE}
        open
        onClose={vi.fn()}
        scopedTenantId="t1"
        onCreated={vi.fn()}
      />,
    );
    const nameInput = await screen.findByLabelText('New process group name');
    fireEvent.change(nameInput, { target: { value: 'Operations' } });
    fireEvent.click(screen.getByRole('button', { name: 'New process group' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('already exists');
    fireEvent.change(nameInput, { target: { value: 'Ops 2' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'New process group' }));
    await waitFor(() => expect(screen.getByLabelText('Process group')).toHaveTextContent('Ops 2'));
    expect(createProcessGroup).toHaveBeenCalledTimes(2);
  });
});

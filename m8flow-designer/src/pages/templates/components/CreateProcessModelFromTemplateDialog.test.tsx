import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { CreateProcessModelFromTemplateDialog } from './CreateProcessModelFromTemplateDialog';
import type { Template } from '@/lib/templatesApi';

vi.mock('@/lib/api', () => ({
  fetchProcessGroups: vi.fn(),
}));

vi.mock('@/lib/templatesApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/templatesApi')>('@/lib/templatesApi');
  return {
    ...actual,
    createProcessModelFromTemplate: vi.fn(),
  };
});

import { fetchProcessGroups } from '@/lib/api';
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
  createdAtInSeconds: 1,
  updatedAtInSeconds: 1,
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
        last_run_in_seconds: null,
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
        created_at_in_seconds: 1,
        updated_at_in_seconds: 1,
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

    await waitFor(() => expect(screen.getByRole('option', { name: 'Finance' })).toBeInTheDocument());
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
});

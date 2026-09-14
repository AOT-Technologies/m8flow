import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Template } from '@/lib/templatesApi';
import { TemplateDetailsPanel } from './TemplateDetailsPanel';

const DRAFT: Template = {
  id: 3,
  templateKey: 'docs-only',
  version: 'V1',
  name: 'Docs Only Template',
  description: 'Markdown pack',
  tags: null,
  category: 'Finance',
  tenantId: 't1',
  visibility: 'PRIVATE',
  files: [{ fileType: 'md', fileName: 'README.md' }],
  isPublished: false,
  status: 'draft',
  createdBy: 'editor',
  modifiedBy: 'editor',
  createdAtInSeconds: 1_700_000_000,
  updatedAtInSeconds: 1_700_000_000,
};

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    clone: () => ({ json: async () => body }),
  };
}

describe('TemplateDetailsPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lets a catalog manager change draft visibility and publish', async () => {
    const onTemplateChange = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
        if (body.is_published === true) {
          return Promise.resolve(jsonResponse({ ...DRAFT, isPublished: true, status: 'published' }));
        }
        if (body.visibility === 'TENANT') {
          return Promise.resolve(jsonResponse({ ...DRAFT, visibility: 'TENANT' }));
        }
        return Promise.resolve(jsonResponse(DRAFT));
      }),
    );

    const { rerender } = render(
      <TemplateDetailsPanel
        template={DRAFT}
        canManage
        onTemplateChange={onTemplateChange}
        onCreateProcessModel={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Docs Only Template' })).toBeInTheDocument();
    expect(screen.getByText('Version V1')).toBeInTheDocument();
    expect(screen.getByText('Finance')).toBeInTheDocument();
    expect(screen.getByText('draft')).toBeInTheDocument();
    expect(screen.getByText('Created by editor')).toBeInTheDocument();
    expect(screen.getByText('Markdown pack')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Create process model' })).toHaveAttribute(
      'title',
      'Process models can only be created from a published template version.',
    );

    fireEvent.change(screen.getByLabelText('Visibility'), { target: { value: 'TENANT' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save visibility' }));
    await waitFor(() => {
      expect(onTemplateChange).toHaveBeenCalledWith(expect.objectContaining({ visibility: 'TENANT' }));
    });
    const visibilityPut = vi.mocked(fetch).mock.calls.find(([, init]) => {
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
      return body.visibility === 'TENANT';
    });
    expect(visibilityPut?.[1]?.method).toBe('PUT');
    expect(String(visibilityPut?.[0])).toContain('/v1.0/m8flow/templates/3');

    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));
    await waitFor(() => {
      expect(onTemplateChange).toHaveBeenCalledWith(
        expect.objectContaining({ isPublished: true, status: 'published' }),
      );
    });
    const publishPut = vi.mocked(fetch).mock.calls.find(([, init]) => {
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
      return body.is_published === true;
    });
    expect(JSON.parse(String(publishPut?.[1]?.body))).toEqual({ is_published: true });

    rerender(
      <TemplateDetailsPanel
        template={{ ...DRAFT, isPublished: true, status: 'published', visibility: 'TENANT' }}
        canManage
        onTemplateChange={onTemplateChange}
        onCreateProcessModel={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Visibility')).not.toBeInTheDocument();
    expect(screen.getByText('TENANT')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).not.toBeDisabled();
    expect(screen.getByText('Saving diagram changes creates a new draft version.')).toBeInTheDocument();
  });

  it('hides mutate actions when the caller cannot manage templates', () => {
    render(
      <TemplateDetailsPanel
        template={DRAFT}
        canManage={false}
        onTemplateChange={vi.fn()}
        onCreateProcessModel={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create process model' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Visibility')).not.toBeInTheDocument();
    expect(screen.getByText('PRIVATE')).toBeInTheDocument();
  });

  it('shows create-from-template without template mutate actions', () => {
    render(
      <TemplateDetailsPanel
        template={{ ...DRAFT, isPublished: true, status: 'published' }}
        canManage={false}
        canCreateProcessModel
        onTemplateChange={vi.fn()}
        onCreateProcessModel={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).not.toBeDisabled();
  });
});

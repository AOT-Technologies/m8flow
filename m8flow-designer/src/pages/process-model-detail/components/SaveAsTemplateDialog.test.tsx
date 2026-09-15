import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import {
  SaveAsTemplateDialog,
  isSupportedTemplateSourceFile,
  mimeForTemplateSourceFile,
  sortFilesPrimaryFirst,
} from './SaveAsTemplateDialog';

describe('save-as-template helpers', () => {
  it('accepts bpmn json dmn md only', () => {
    expect(isSupportedTemplateSourceFile('a.bpmn')).toBe(true);
    expect(isSupportedTemplateSourceFile('form.json')).toBe(true);
    expect(isSupportedTemplateSourceFile('rules.dmn')).toBe(true);
    expect(isSupportedTemplateSourceFile('notes.md')).toBe(true);
    expect(isSupportedTemplateSourceFile('skip.txt')).toBe(false);
  });

  it('picks mime from extension', () => {
    expect(mimeForTemplateSourceFile('a.json')).toBe('application/json');
    expect(mimeForTemplateSourceFile('a.md')).toBe('text/markdown');
    expect(mimeForTemplateSourceFile('a.bpmn')).toBe('application/xml');
  });

  it('moves the primary file to the front', () => {
    const files = [{ name: 'form.json' }, { name: 'main.bpmn' }, { name: 'notes.md' }];
    expect(sortFilesPrimaryFirst(files, 'main.bpmn').map((f) => f.name)).toEqual([
      'main.bpmn',
      'form.json',
      'notes.md',
    ]);
  });
});

describe('SaveAsTemplateDialog', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('creates a draft from name, visibility, tags, and packed files', async () => {
    const getFiles = vi.fn().mockResolvedValue([
      { name: 'invoice.bpmn', content: new Blob(['<bpmn/>'], { type: 'application/xml' }) },
    ]);
    const onCreated = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 42 }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <SaveAsTemplateDialog
        open
        onClose={vi.fn()}
        defaultName="Invoice Approval"
        getFiles={getFiles}
        onCreated={onCreated}
      />,
    );

    expect(screen.getByLabelText('Name')).toHaveValue('Invoice Approval');
    fireEvent.change(screen.getByLabelText('Description (optional)'), {
      target: { value: 'From the catalog model' },
    });
    fireEvent.change(screen.getByLabelText('Category (optional)'), { target: { value: 'Finance' } });
    fireEvent.change(screen.getByLabelText('Tags (comma-separated, optional)'), {
      target: { value: 'invoices, approval' },
    });
    fireEvent.change(screen.getByLabelText('Visibility'), { target: { value: 'TENANT' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create template' }));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(42);
    });
    expect(getFiles).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain('/v1.0/m8flow/templates');
    expect(init.method).toBe('POST');
    const headers = new Headers(init.headers);
    expect(headers.get('X-Template-Key')).toBe('invoice-approval');
    expect(headers.get('X-Template-Name')).toBe('Invoice Approval');
    expect(headers.get('X-Template-Description')).toBe('From the catalog model');
    expect(headers.get('X-Template-Category')).toBe('Finance');
    expect(headers.get('X-Template-Visibility')).toBe('TENANT');
    expect(headers.get('X-Template-Tags')).toBe(JSON.stringify(['invoices', 'approval']));
    expect(init.body).toBeInstanceOf(FormData);
  });

  it('rejects names the host would reject', async () => {
    render(
      <SaveAsTemplateDialog
        open
        onClose={vi.fn()}
        defaultName="Bad@Name"
        getFiles={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create template' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/letters, numbers, spaces/);
  });

  it('surfaces a host duplicate-name message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        clone: () => ({
          json: async () => ({
            error_code: 'template_name_exists',
            message: "A template named 'Invoice Approval' already exists. Please choose a different name.",
          }),
        }),
      }),
    );
    render(
      <SaveAsTemplateDialog
        open
        onClose={vi.fn()}
        defaultName="Invoice Approval"
        getFiles={async () => [
          { name: 'a.bpmn', content: new Blob(['x'], { type: 'application/xml' }) },
        ]}
        onCreated={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create template' }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/already exists/);
    });
    expect(ApiError).toBeDefined();
  });
});

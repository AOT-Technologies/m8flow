import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import { activeTenantFromContext, capabilitiesFromContext } from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => ({
    tenants: [],
    refreshTenants: () => {},
    organizationMemberships: [],
    activeTenantLabel: null,
  }),
}));
import type { Template } from '@/lib/templatesApi';
import TemplateModelerPage from './TemplateModelerPage';

function renderAt(
  templateId: string,
  context: SessionFixtureContext = {
    scopedTenantId: null,
    selectedTenantId: null,
    isSuperAdmin: false,
    canManageProcesses: true,
  },
) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={[`/templates/${templateId}`]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/templates/:templateId" element={<TemplateModelerPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    clone: () => ({ json: async () => body }),
  };
}

const DOCS_ONLY: Template = {
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

const PUBLISHED_V1: Template = {
  ...DOCS_ONLY,
  id: 1,
  version: 'V1',
  isPublished: true,
  status: 'published',
  files: [{ fileType: 'bpmn', fileName: 'flow.bpmn' }],
};

const DRAFT_V2: Template = {
  ...DOCS_ONLY,
  id: 2,
  version: 'V2',
  isPublished: false,
  status: 'draft',
  files: [{ fileType: 'md', fileName: 'README.md' }],
};

function stubTemplateFetch(
  byId: Record<number, Template>,
  extra: { versions?: Template[]; put?: Template } = {},
) {
  const versions = extra.versions ?? Object.values(byId);
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const href = String(url);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method === 'PUT') {
      return Promise.resolve(
        jsonResponse(extra.put ?? { ...Object.values(byId)[0], isPublished: true, status: 'published' }),
      );
    }
    if (method === 'POST' && href.includes('/create-process-model')) {
      return Promise.resolve(
        jsonResponse({
          process_model: { id: 'finance/from-template' },
          template_info: {},
        }),
      );
    }
    if (href.includes('/process-groups')) {
      return Promise.resolve(
        jsonResponse([
          {
            id: 'finance',
            display_name: 'Finance',
            description: '',
            model_count: 1,
            last_run_in_seconds: null,
          },
        ]),
      );
    }
    if (href.includes('/v1.0/m8flow/templates?')) {
      return Promise.resolve(
        jsonResponse({
          results: versions,
          pagination: { count: versions.length, total: versions.length, pages: 1 },
        }),
      );
    }
    const idMatch = href.match(/\/templates\/(\d+)/);
    const id = idMatch ? Number(idMatch[1]) : NaN;
    const found = byId[id];
    if (!found) {
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}), clone: () => ({ json: async () => ({}) }) });
    }
    return Promise.resolve(jsonResponse(found));
  });
}

describe('TemplateModelerPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows "Template not found" for a non-numeric id without fetching', () => {
    renderAt('not-a-number');
    expect(screen.getByText('Template not found.')).toBeInTheDocument();
  });

  it('shows "Template not found" when the backend 404s', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));

    renderAt('999');

    await waitFor(() => {
      expect(screen.getByText('Template not found.')).toBeInTheDocument();
    });
  });

  it('shows a visible error for a non-404 fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    renderAt('7');

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('GET');
    });
  });

  it('lists files that open in the per-file modeler', async () => {
    const withFiles = {
      ...DOCS_ONLY,
      files: [
        { fileType: 'md' as const, fileName: 'README.md' },
        { fileType: 'bpmn' as const, fileName: 'flow.bpmn' },
        { fileType: 'json' as const, fileName: 'task-schema.json' },
      ],
    };
    vi.stubGlobal('fetch', stubTemplateFetch({ 3: withFiles }));

    renderAt('3');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Docs Only Template' })).toBeInTheDocument();
    });
    expect(screen.queryByLabelText('All versions')).not.toBeInTheDocument();
    expect(screen.getByText('README.md')).toBeInTheDocument();
    expect(screen.getByText('flow.bpmn')).toBeInTheDocument();
    expect(screen.getByText('task-schema.json')).toBeInTheDocument();
    const editLinks = screen.getAllByTitle('Edit file');
    expect(editLinks.map((link) => link.getAttribute('href'))).toEqual([
      '/templates/3/modeler/README.md',
      '/templates/3/modeler/flow.bpmn',
      '/templates/3/modeler/task-schema.json',
    ]);
    expect(screen.getByText('Primary')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).toBeDisabled();
  });

  it('publishes a draft from the details panel', async () => {
    vi.stubGlobal(
      'fetch',
      stubTemplateFetch(
        { 3: DOCS_ONLY },
        { put: { ...DOCS_ONLY, isPublished: true, status: 'published' } },
      ),
    );

    renderAt('3');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Publish' })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }));
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Create process model' })).not.toBeDisabled();
    expect(screen.getByText('PRIVATE')).toBeInTheDocument();
    const put = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'PUT');
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ is_published: true });
  });

  it('keeps publish and visibility mutate hidden for super-admin but allows create-from-template', async () => {
    vi.stubGlobal('fetch', stubTemplateFetch({ 3: DOCS_ONLY }));

    renderAt('3', {
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
      canManageProcesses: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Docs Only Template' })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: 'Publish' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).toBeDisabled();
    expect(screen.queryByLabelText('Visibility')).not.toBeInTheDocument();
    expect(screen.getByText('PRIVATE')).toBeInTheDocument();
  });

  it('switches versions and updates the file list', async () => {
    vi.stubGlobal(
      'fetch',
      stubTemplateFetch(
        { 1: PUBLISHED_V1, 2: DRAFT_V2 },
        { versions: [PUBLISHED_V1, DRAFT_V2] },
      ),
    );

    renderAt('2');

    await waitFor(() => {
      expect(screen.getByLabelText('All versions')).toBeInTheDocument();
    });
    expect(
      vi.mocked(fetch).mock.calls.some(
        ([url]) => String(url).includes('latest_only=false') && String(url).includes('template_key=docs-only'),
      ),
    ).toBe(true);
    expect(screen.getByText('README.md')).toBeInTheDocument();
    expect(screen.queryByText('flow.bpmn')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('All versions'), { target: { value: '1' } });

    await waitFor(() => {
      expect(screen.getByText('flow.bpmn')).toBeInTheDocument();
    });
    expect(screen.queryByText('README.md')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create process model' })).not.toBeDisabled();
    const editLinks = screen.getAllByTitle('Edit file');
    expect(editLinks.map((link) => link.getAttribute('href'))).toEqual(['/templates/1/modeler/flow.bpmn']);
  });

  it('creates a process model from the selected published version', async () => {
    vi.stubGlobal(
      'fetch',
      stubTemplateFetch(
        { 1: PUBLISHED_V1, 2: DRAFT_V2 },
        { versions: [PUBLISHED_V1, DRAFT_V2] },
      ),
    );

    renderAt('2');

    await waitFor(() => {
      expect(screen.getByLabelText('All versions')).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText('All versions'), { target: { value: '1' } });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Create process model' })).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Copies every file from/)).toHaveTextContent('vV1');
    await waitFor(() => {
      expect(within(dialog).getByLabelText('Process group')).toHaveValue('finance');
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create process model' }));

    await waitFor(() => {
      const createCall = vi.mocked(fetch).mock.calls.find(
        ([url, init]) => String(url).includes('/create-process-model') && init?.method === 'POST',
      );
      expect(createCall).toBeTruthy();
      expect(String(createCall?.[0])).toContain('/v1.0/m8flow/templates/1/create-process-model');
    });
  });
});

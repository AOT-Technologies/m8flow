import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { forwardRef, useImperativeHandle, type Ref } from 'react';
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
import type { DiagramCanvasHandle } from '@/pages/process-model-modeler/components/DiagramCanvasHandle';

vi.mock('@/pages/process-model-modeler/components/DiagramCanvas', () => ({
  DiagramCanvas: forwardRef(function DiagramCanvasStub(
    {
      fileName,
      xml,
      onDirtyChange,
    }: {
      fileName: string;
      xml: string;
      onDirtyChange?: (dirty: boolean) => void;
    },
    ref: Ref<DiagramCanvasHandle>,
  ) {
    useImperativeHandle(ref, () => ({
      saveXML: async () => ({ xml, baseline: xml }),
      markSaved: () => {
        onDirtyChange?.(false);
        return false;
      },
    }));
    return (
      <div>
        <button type="button" onClick={() => onDirtyChange?.(true)}>
          Mark dirty
        </button>
        canvas-ready {fileName}
      </div>
    );
  }),
}));

import TemplateFileModelerPage from './TemplateFileModelerPage';

const TEMPLATE = {
  id: 3,
  templateKey: 'invoice',
  version: 'V1',
  name: 'Invoice Template',
  description: null,
  tags: null,
  category: null,
  tenantId: 't1',
  visibility: 'TENANT',
  files: [
    { fileType: 'bpmn', fileName: 'flow.bpmn' },
    { fileType: 'json', fileName: 'task-schema.json' },
    { fileType: 'md', fileName: 'README.md' },
  ],
  isPublished: false,
  status: 'draft',
  createdBy: 'editor',
  modifiedBy: 'editor',
  createdAtInSeconds: 1_700_000_000,
  updatedAtInSeconds: 1_700_000_000,
};

function renderAt(
  path: string,
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
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/templates/:templateId" element={<p>Template detail</p>} />
          <Route
            path="/templates/:templateId/modeler/:fileName"
            element={<TemplateFileModelerPage />}
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('TemplateFileModelerPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens a markdown file and saves it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        const path = String(url);
        if (path.includes('/files/README.md') && init?.method === 'PUT') {
          return Promise.resolve({
            ok: true,
            json: async () => TEMPLATE,
          });
        }
        if (path.includes('/files/README.md')) {
          return Promise.resolve({
            ok: true,
            text: async () => '# Hello',
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => TEMPLATE,
        });
      }),
    );

    renderAt('/templates/3/modeler/README.md');
    expect(await screen.findByText('canvas-ready README.md')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mark dirty' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      const put = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'PUT');
      expect(put).toBeDefined();
      expect(String(put?.[0])).toContain('/v1.0/m8flow/templates/3/files/README.md');
    });
  });

  it('re-anchors on the forked draft id after saving a published template', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        const path = String(url);
        if (init?.method === 'PUT') {
          return Promise.resolve({
            ok: true,
            json: async () => ({ ...TEMPLATE, id: 9, isPublished: false, version: 'V2', status: 'draft' }),
          });
        }
        if (path.includes('/files/flow.bpmn')) {
          return Promise.resolve({
            ok: true,
            text: async () => '<bpmn/>',
          });
        }
        if (path.includes('/templates/9')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ ...TEMPLATE, id: 9, isPublished: false, version: 'V2' }),
            text: async () => '<bpmn/>',
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ ...TEMPLATE, isPublished: true, status: 'published' }),
        });
      }),
    );

    renderAt('/templates/3/modeler/flow.bpmn');
    expect(await screen.findByText('canvas-ready flow.bpmn')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mark dirty' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Invoice Template' })).toHaveAttribute('href', '/templates/9');
    });
  });

  it('shows file not found when the file is missing from the template', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => TEMPLATE,
      }),
    );

    renderAt('/templates/3/modeler/missing.bpmn');
    expect(await screen.findByText('File not found.')).toBeInTheDocument();
  });
});

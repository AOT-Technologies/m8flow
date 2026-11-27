import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { forwardRef, useImperativeHandle, useState, type Ref } from 'react';
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
    const [draft, setDraft] = useState(xml);
    // Sync only when the prop changes: a mount effect could land after the test types and wipe the draft.
    const [seenXml, setSeenXml] = useState(xml);
    if (xml !== seenXml) {
      setSeenXml(xml);
      setDraft(xml);
    }
    useImperativeHandle(ref, () => ({
      saveXML: async () => ({ xml: draft, baseline: draft }),
      markSaved: () => {
        onDirtyChange?.(false);
        return false;
      },
    }));
    return (
      <div>
        <textarea aria-label="Canvas draft" value={draft} onChange={(event) => {
          setDraft(event.target.value);
          onDirtyChange?.(true);
        }} />
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
  createdAt: new Date(1_700_000_000 * 1000).toISOString(),
  updatedAt: new Date(1_700_000_000 * 1000).toISOString(),
};

function renderAt(
  path: string,
  context: SessionFixtureContext = {
    scopedTenantId: null,
    selectedTenantId: null,
    activeTenantId: 't1',
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
  it('keeps edits and shows the connection message after a failed save, then retries on Save', async () => {
    let saves = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        saves += 1;
        if (saves === 1) throw new TypeError('Load failed');
        return { ok: true, json: async () => TEMPLATE };
      }
      if (url.includes('/files/README.md')) return { ok: true, text: async () => '# Original' };
      return { ok: true, json: async () => TEMPLATE };
    });
    vi.stubGlobal('fetch', fetchMock);
    renderAt('/templates/3/modeler/README.md');
    const draft = await screen.findByLabelText('Canvas draft');
    fireEvent.change(draft, { target: { value: '# Unsaved draft' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to connect.');
    expect(screen.getByLabelText('Canvas draft')).toBe(draft);
    expect(draft).toHaveValue('# Unsaved draft');
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    window.dispatchEvent(new Event('online'));
    expect(saves).toBe(1);
    fireEvent.click(await screen.findByRole('button', { name: 'Save' }));
    await waitFor(() => expect(saves).toBe(2));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(draft).toHaveValue('# Unsaved draft');
    const puts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'PUT');
    expect(puts[1][1]?.body).toBe('# Unsaved draft');
  });
  it('guards unload while a save is in flight and releases it once saved', async () => {
    let finishSave: (() => void) | undefined;
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return new Promise((resolve) => {
          finishSave = () => resolve({ ok: true, json: async () => TEMPLATE });
        });
      }
      if (url.includes('/files/README.md')) return Promise.resolve({ ok: true, text: async () => '# Original' });
      return Promise.resolve({ ok: true, json: async () => TEMPLATE });
    }));
    renderAt('/templates/3/modeler/README.md');
    fireEvent.change(await screen.findByLabelText('Canvas draft'), { target: { value: '# Draft' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(finishSave).toBeDefined());
    const during = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(during);
    expect(during.defaultPrevented).toBe(true);
    finishSave?.();
    await waitFor(() => {
      const after = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(after);
      expect(after.defaultPrevented).toBe(false);
    });
  });
  afterEach(() => {
    // Unmount before restoring: a late fetch would otherwise re-render the page against reset session-hook mocks.
    cleanup();
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

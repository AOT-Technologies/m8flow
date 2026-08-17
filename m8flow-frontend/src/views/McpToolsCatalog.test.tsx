import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import McpToolsCatalog from './McpToolsCatalog';

const h = vi.hoisted(() => ({
  canAccess: true,
  canExecute: true,
  catalogResponse: null as any,
  pingResponse: null as any,
  executeResponse: null as any,
  executeFailure: null as any,
  makeCallToBackend: vi.fn(),
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET', POST: 'POST' },
    makeCallToBackend: (opts: any) => {
      h.makeCallToBackend(opts);
      if (opts.path === '/m8flow/mcp-tools' && (!opts.httpMethod || opts.httpMethod === 'GET')) {
        opts.successCallback(h.catalogResponse);
      } else if (opts.path === '/m8flow/mcp-tools/ping') {
        opts.successCallback(h.pingResponse);
      } else if (opts.path === '/m8flow/mcp-tools/execute') {
        if (h.executeFailure) {
          opts.failureCallback(h.executeFailure);
        } else {
          opts.successCallback(h.executeResponse);
        }
      }
    },
  },
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: {
      can: (verb: string) => (verb === 'POST' ? h.canExecute : h.canAccess),
    },
    permissionsLoaded: true,
  })),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: vi.fn(() => ({
    targetUris: {
      m8flowMcpToolsCatalogPath: '/m8flow/mcp-tools',
      m8flowMcpToolsExecutePath: '/m8flow/mcp-tools/execute',
    },
  })),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key} ${JSON.stringify(opts)}` : key,
  }),
}));

vi.mock('../helpers', () => ({ setPageTitle: vi.fn() }));

vi.mock('@mui/icons-material', () => {
  const Icon = () => null;
  return new Proxy(
    { __esModule: true },
    {
      get: (_target, prop) => {
        if (prop === '__esModule') return true;
        if (prop === 'then' || typeof prop === 'symbol') return undefined;
        return Icon;
      },
      has: () => true,
    },
  );
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <McpToolsCatalog />
    </MemoryRouter>,
  );

beforeEach(() => {
  h.canAccess = true;
  h.canExecute = true;
  h.executeFailure = null;
  h.makeCallToBackend.mockClear();
  h.catalogResponse = {
    server_url: 'https://qa.m8flow.ai/mcp',
    protocol_version: '2025-06-18',
    tool_count: 3,
    tools: [
      {
        name: 'list_things',
        description: 'List all the things',
        category: 'things',
        badge: 'read',
        parameters: [],
      },
      {
        name: 'create_thing',
        description: 'Create a new thing',
        category: 'things',
        badge: 'write',
        parameters: [
          { name: 'name', type: 'string', required: true, description: 'Thing name' },
          { name: 'payload', type: 'object', required: false, description: 'Extra data' },
        ],
      },
      {
        name: 'get_secret_value',
        description: 'Returns a decrypted secret',
        category: 'secrets',
        badge: 'read',
        parameters: [],
      },
    ],
  };
  h.pingResponse = {
    ok: true,
    latency_ms: 212,
    protocol_version: '2025-06-18',
    authorized: true,
  };
  h.executeResponse = { result: { ok: true } };
});

describe('McpToolsCatalog', () => {
  it('redirects away when the user lacks permission', () => {
    h.canAccess = false;
    renderPage();
    expect(screen.queryByTestId('mcp-tools-catalog-page')).toBeNull();
  });

  it('loads and shows the catalog header (server URL, protocol, tool count, ping)', async () => {
    renderPage();
    expect(await screen.findByTestId('mcp-tools-server-url')).toHaveTextContent(
      'https://qa.m8flow.ai/mcp',
    );
    expect(screen.getByTestId('mcp-tools-protocol-version')).toHaveTextContent('2025-06-18');
    expect(screen.getByTestId('mcp-tools-tool-count')).toHaveTextContent('3');
    await waitFor(() =>
      expect(screen.getByTestId('mcp-tools-ping-status')).toHaveTextContent('212'),
    );
    expect(screen.getByTestId('mcp-tools-authorized-chip')).toBeInTheDocument();
  });

  it('renders every tool grouped by category', async () => {
    renderPage();
    expect(await screen.findByTestId('mcp-tool-list_things')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-tool-create_thing')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-tool-get_secret_value')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-tools-category-heading-things')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-tools-category-heading-secrets')).toBeInTheDocument();
  });

  it('filters tools by the search box', async () => {
    renderPage();
    await screen.findByTestId('mcp-tool-list_things');
    fireEvent.change(screen.getByTestId('mcp-tools-search-input').querySelector('input')!, {
      target: { value: 'secret' },
    });
    expect(screen.queryByTestId('mcp-tool-list_things')).toBeNull();
    expect(screen.getByTestId('mcp-tool-get_secret_value')).toBeInTheDocument();
  });

  it('executes a read tool immediately without a confirmation dialog', async () => {
    renderPage();
    await screen.findByTestId('mcp-tool-list_things');
    fireEvent.click(screen.getByTestId('mcp-tool-execute-list_things'));

    await waitFor(() =>
      expect(h.makeCallToBackend).toHaveBeenCalledWith(
        expect.objectContaining({
          path: '/m8flow/mcp-tools/execute',
          httpMethod: 'POST',
          postBody: { tool_name: 'list_things', arguments: {}, confirm: false },
        }),
      ),
    );
    expect(await screen.findByTestId('mcp-tool-result-list_things')).toHaveTextContent('true');
  });

  it('requires confirmation before executing a write tool, then sends confirm=true', async () => {
    renderPage();
    await screen.findByTestId('mcp-tool-create_thing');

    fireEvent.change(
      screen.getByTestId('mcp-tool-param-create_thing-name').querySelector('input')!,
      { target: { value: 'widget' } },
    );
    fireEvent.click(screen.getByTestId('mcp-tool-execute-create_thing'));

    // No execute call yet -- the confirm dialog must appear first.
    expect(h.makeCallToBackend).not.toHaveBeenCalledWith(
      expect.objectContaining({ path: '/m8flow/mcp-tools/execute' }),
    );
    const confirmButton = await screen.findByTestId('mcp-tool-confirm-run-create_thing');
    fireEvent.click(confirmButton);

    await waitFor(() =>
      expect(h.makeCallToBackend).toHaveBeenCalledWith(
        expect.objectContaining({
          path: '/m8flow/mcp-tools/execute',
          postBody: { tool_name: 'create_thing', arguments: { name: 'widget' }, confirm: true },
        }),
      ),
    );
  });

  it('blocks execution with a "field required" error when a required param is empty', async () => {
    renderPage();
    await screen.findByTestId('mcp-tool-create_thing');

    // `name` is required and deliberately left empty.
    fireEvent.click(screen.getByTestId('mcp-tool-execute-create_thing'));
    fireEvent.click(await screen.findByTestId('mcp-tool-confirm-run-create_thing'));

    expect(await screen.findByText('mcp_tools_field_required')).toBeInTheDocument();
    expect(screen.queryByText('mcp_tools_invalid_json')).toBeNull();
    expect(h.makeCallToBackend).not.toHaveBeenCalledWith(
      expect.objectContaining({ path: '/m8flow/mcp-tools/execute' }),
    );
  });

  it('blocks execution with an "invalid json" error when an object param is malformed', async () => {
    renderPage();
    await screen.findByTestId('mcp-tool-create_thing');

    fireEvent.change(
      screen.getByTestId('mcp-tool-param-create_thing-name').querySelector('input')!,
      { target: { value: 'widget' } },
    );
    fireEvent.change(
      screen.getByTestId('mcp-tool-param-create_thing-payload').querySelector('textarea')!,
      { target: { value: '{not json' } },
    );
    fireEvent.click(screen.getByTestId('mcp-tool-execute-create_thing'));
    fireEvent.click(await screen.findByTestId('mcp-tool-confirm-run-create_thing'));

    expect(await screen.findByText('mcp_tools_invalid_json')).toBeInTheDocument();
    expect(screen.queryByText('mcp_tools_field_required')).toBeNull();
    expect(h.makeCallToBackend).not.toHaveBeenCalledWith(
      expect.objectContaining({ path: '/m8flow/mcp-tools/execute' }),
    );
  });

  it('shows an error message when execution fails', async () => {
    h.executeFailure = { message: 'boom' };
    renderPage();
    await screen.findByTestId('mcp-tool-list_things');
    fireEvent.click(screen.getByTestId('mcp-tool-execute-list_things'));
    expect(await screen.findByTestId('mcp-tool-error-list_things')).toHaveTextContent('boom');
  });

  it('disables Execute (but still shows the tool) when the user cannot execute tools', async () => {
    h.canExecute = false;
    renderPage();
    await screen.findByTestId('mcp-tool-list_things');
    expect(screen.getByTestId('mcp-tools-read-only-notice')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-tool-execute-list_things')).toBeDisabled();
  });

  it('shows an error banner when the catalog fails to load', async () => {
    h.catalogResponse = null;
    vi.mocked(await import('../services/HttpService')).default.makeCallToBackend = ((opts: any) => {
      if (opts.path === '/m8flow/mcp-tools') {
        opts.failureCallback();
      } else {
        opts.successCallback(h.pingResponse);
      }
    }) as any;
    renderPage();
    expect(await screen.findByTestId('mcp-tools-catalog-error')).toBeInTheDocument();
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import McpConnection from './McpConnection';

const h = vi.hoisted(() => ({
  mcpServerUrl: 'https://qa.m8flow.ai/mcp',
  canAccess: true,
  clipboardWriteText: (() => Promise.resolve()) as (text: string) => Promise<void>,
}));

vi.mock('../utils/useConfig', () => ({
  useConfig: () => ({
    MCP_SERVER_URL: h.mcpServerUrl,
    MCP_CONNECTION_ENABLED: Boolean(h.mcpServerUrl),
  }),
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: () => h.canAccess },
    permissionsLoaded: true,
  })),
}));

vi.mock('../hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: vi.fn(() => ({
    targetUris: {
      m8flowMcpConnectionPath: '/m8flow/mcp-connection',
    },
  })),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../helpers', () => ({ setPageTitle: vi.fn() }));

vi.mock('@mui/icons-material', () => {
  const Icon = () => null;
  return new Proxy(
    { __esModule: true },
    {
      get: (_target, prop) => {
        if (prop === '__esModule') return true;
        // Must NOT return a function for `then` (or symbols) or the mocked
        // module namespace looks like a never-resolving thenable and vitest
        // hangs awaiting it during collection.
        if (prop === 'then' || typeof prop === 'symbol') return undefined;
        return Icon;
      },
      // vitest validates accessed exports with `prop in module` and throws
      // "No <name> export is defined" otherwise — report every icon as present.
      has: () => true,
    },
  );
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <McpConnection />
    </MemoryRouter>,
  );

beforeEach(() => {
  h.mcpServerUrl = 'https://qa.m8flow.ai/mcp';
  h.canAccess = true;
  h.clipboardWriteText = vi.fn(() => Promise.resolve());
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: h.clipboardWriteText },
    configurable: true,
  });
});

describe('McpConnection', () => {
  it('shows the configured MCP server URL with client setup sections', () => {
    renderPage();
    expect(screen.getByTestId('mcp-server-url')).toHaveTextContent(
      'https://qa.m8flow.ai/mcp',
    );
    expect(screen.getByTestId('mcp-client-cursor')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-client-claude-code')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-client-other')).toBeInTheDocument();
  });

  it('interpolates the URL into the client config snippets', () => {
    renderPage();
    expect(screen.getByTestId('mcp-snippet-cursor')).toHaveTextContent(
      '"url": "https://qa.m8flow.ai/mcp"',
    );
    expect(screen.getByTestId('mcp-snippet-claude-code')).toHaveTextContent(
      'claude mcp add --transport http m8flow https://qa.m8flow.ai/mcp',
    );
  });

  it('copies the server URL to the clipboard', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('mcp-server-url-copy'));
    await waitFor(() =>
      expect(h.clipboardWriteText).toHaveBeenCalledWith(
        'https://qa.m8flow.ai/mcp',
      ),
    );
  });

  it('shows a warning instead of instructions when no URL is configured', () => {
    h.mcpServerUrl = '';
    renderPage();
    expect(screen.getByTestId('mcp-not-configured')).toBeInTheDocument();
    expect(screen.queryByTestId('mcp-server-url')).toBeNull();
  });

  it('redirects away when the user lacks permission', () => {
    h.canAccess = false;
    renderPage();
    expect(screen.queryByTestId('mcp-connection-page')).toBeNull();
  });
});

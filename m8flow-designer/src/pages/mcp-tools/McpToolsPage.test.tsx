import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';

const api = { fetchMcpToolsCatalog: vi.fn(), pingMcpServer: vi.fn(), executeMcpTool: vi.fn() };
vi.mock('@/lib/mcpToolsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/mcpToolsApi')>('@/lib/mcpToolsApi');
  return {
    ...actual,
    fetchMcpToolsCatalog: () => api.fetchMcpToolsCatalog(),
    pingMcpServer: () => api.pingMcpServer(),
    executeMcpTool: (...args: unknown[]) => api.executeMcpTool(...args),
  };
});

const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({ useCapabilities: () => mockUseCapabilities() }));

import McpToolsPage from './McpToolsPage';

const tool = (name: string, category: string, badge: 'read' | 'write' = 'read', parameters: unknown[] = []) => ({
  name,
  description: `${name} description`,
  category,
  badge,
  parameters,
});

const catalog = {
  server_url: 'http://mcp.test/mcp',
  protocol_version: '2025-06-18',
  tool_count: 3,
  tools: [
    tool('list_process_models', 'process-models', 'read', [
      { name: 'page', type: 'integer', required: false, description: 'Page number' },
    ]),
    tool('start_process_instance', 'process-instances', 'write'),
    tool('list_tasks', 'tasks'),
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCapabilities.mockReturnValue({ canExecuteMcpTools: true });
  api.fetchMcpToolsCatalog.mockResolvedValue(catalog);
  api.pingMcpServer.mockResolvedValue({ ok: true, latency_ms: 12, protocol_version: '2025-06-18', authorized: true });
});

describe('McpToolsPage', () => {
  it('lists tools grouped by category with server info and ping status', async () => {
    render(<McpToolsPage />);
    expect(await screen.findByText('list_process_models')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Process Instances' })).toHaveTextContent('start_process_instance');
    expect(screen.getByTestId('mcp-tools-server-info')).toHaveTextContent(
      'http://mcp.test/mcp · Protocol 2025-06-18 · 3 tools',
    );
    expect(await screen.findByText('Connected · 12 ms')).toBeInTheDocument();
  });

  it('shows the backend reason and the ping result when the catalog fails (M8F-539)', async () => {
    api.fetchMcpToolsCatalog.mockRejectedValue(
      new ApiError('/v1.0/m8flow/mcp-tools', 502, 'GET', 'Not authorized to reach the MCP server (HTTP 401).'),
    );
    api.pingMcpServer.mockResolvedValue({ ok: false, latency_ms: 30, protocol_version: null, authorized: false });
    render(<McpToolsPage />);
    const alert = await screen.findByTestId('mcp-tools-catalog-error');
    expect(alert).toHaveTextContent('Could not load the MCP tools catalog.');
    expect(alert).toHaveTextContent('Not authorized to reach the MCP server (HTTP 401).');
    expect(await screen.findByText('Not authorized')).toBeInTheDocument();
  });

  it('Test connection re-pings and retries a failed catalog', async () => {
    api.fetchMcpToolsCatalog.mockRejectedValueOnce(
      new ApiError('/v1.0/m8flow/mcp-tools', 503, 'GET', 'M8FLOW_MCP_SERVER_URL is not configured.'),
    );
    render(<McpToolsPage />);
    expect(await screen.findByTestId('mcp-tools-catalog-error')).toHaveTextContent(
      'M8FLOW_MCP_SERVER_URL is not configured.',
    );
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }));
    expect(await screen.findByText('list_process_models')).toBeInTheDocument();
    expect(screen.queryByTestId('mcp-tools-catalog-error')).not.toBeInTheDocument();
    expect(api.pingMcpServer).toHaveBeenCalledTimes(2);
  });

  it('filters by search text and by category', async () => {
    render(<McpToolsPage />);
    await screen.findByText('list_process_models');
    await userEvent.type(screen.getByPlaceholderText('Search tools…'), 'tasks');
    expect(screen.getByText('list_tasks')).toBeInTheDocument();
    expect(screen.queryByText('list_process_models')).not.toBeInTheDocument();
    await userEvent.clear(screen.getByPlaceholderText('Search tools…'));
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'process-instances');
    expect(screen.getByText('start_process_instance')).toBeInTheDocument();
    expect(screen.queryByText('list_tasks')).not.toBeInTheDocument();
  });

  it('expands a tool to show its parameters', async () => {
    render(<McpToolsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /list_process_models/ }));
    const row = screen.getByRole('row', { name: /page/ });
    expect(row).toHaveTextContent('integer');
    expect(row).toHaveTextContent('optional');
  });

  it('hides Try it and explains why when execute is not granted', async () => {
    mockUseCapabilities.mockReturnValue({ canExecuteMcpTools: false });
    render(<McpToolsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /list_process_models/ }));
    expect(screen.getByTestId('mcp-tools-read-only-notice')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Execute' })).not.toBeInTheDocument();
  });

  it('shows Try it inside an expanded tool when execute is granted', async () => {
    render(<McpToolsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /list_process_models/ }));
    expect(screen.getByRole('button', { name: 'Execute' })).toBeInTheDocument();
    expect(screen.queryByTestId('mcp-tools-read-only-notice')).not.toBeInTheDocument();
  });
});

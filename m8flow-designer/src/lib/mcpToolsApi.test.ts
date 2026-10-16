import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
const apiPost = vi.fn();
vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return { ...actual, apiGet: (...a: unknown[]) => apiGet(...a), apiPost: (...a: unknown[]) => apiPost(...a) };
});

import { ApiError } from './api';
import { executeMcpTool, fetchMcpToolsCatalog, mcpErrorMessage, pingMcpServer } from './mcpToolsApi';

beforeEach(() => vi.clearAllMocks());

describe('mcpToolsApi', () => {
  it('calls the three backend routes', async () => {
    await fetchMcpToolsCatalog();
    await pingMcpServer();
    await executeMcpTool('cancel_process_instance', { process_instance_id: 7 }, true);
    expect(apiGet).toHaveBeenNthCalledWith(1, '/v1.0/m8flow/mcp-tools');
    expect(apiGet).toHaveBeenNthCalledWith(2, '/v1.0/m8flow/mcp-tools/ping');
    expect(apiPost).toHaveBeenCalledWith('/v1.0/m8flow/mcp-tools/execute', {
      tool_name: 'cancel_process_instance',
      arguments: { process_instance_id: 7 },
      confirm: true,
    });
  });

  it('prefers the backend reason over the fallback', () => {
    const err = new ApiError('/v1.0/m8flow/mcp-tools', 503, 'GET', 'M8FLOW_MCP_SERVER_URL is not configured.');
    expect(mcpErrorMessage(err, 'fallback')).toBe('M8FLOW_MCP_SERVER_URL is not configured.');
    expect(mcpErrorMessage(new ApiError('/x', 500), 'fallback')).toBe('fallback');
    expect(mcpErrorMessage(new TypeError('network'), 'fallback')).toBe('fallback');
  });
});

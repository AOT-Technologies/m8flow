import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { McpTool } from '@/lib/mcpToolsApi';

const api = { executeMcpTool: vi.fn() };
vi.mock('@/lib/mcpToolsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/mcpToolsApi')>('@/lib/mcpToolsApi');
  return { ...actual, executeMcpTool: (...args: unknown[]) => api.executeMcpTool(...args) };
});

import { McpToolTryIt } from './McpToolTryIt';

const readTool: McpTool = {
  name: 'get_process_instance',
  description: '',
  category: 'process-instances',
  badge: 'read',
  parameters: [{ name: 'process_instance_id', type: 'integer', required: true, description: '' }],
};
const writeTool: McpTool = { ...readTool, name: 'cancel_process_instance', badge: 'write' };

beforeEach(() => vi.clearAllMocks());

describe('McpToolTryIt', () => {
  it('runs a read tool immediately with typed arguments', async () => {
    api.executeMcpTool.mockResolvedValue({ result: { id: 7 } });
    render(<McpToolTryIt tool={readTool} />);
    await userEvent.type(screen.getByLabelText(/process_instance_id/), '7');
    await userEvent.click(screen.getByRole('button', { name: 'Execute' }));
    expect(api.executeMcpTool).toHaveBeenCalledWith('get_process_instance', { process_instance_id: 7 }, false);
    expect(await screen.findByTestId('mcp-tool-result')).toHaveTextContent('"id": 7');
  });

  it('blocks a missing required field', async () => {
    render(<McpToolTryIt tool={readTool} />);
    await userEvent.click(screen.getByRole('button', { name: 'Execute' }));
    expect(screen.getByText('This field is required.')).toBeInTheDocument();
    expect(api.executeMcpTool).not.toHaveBeenCalled();
  });

  it('asks before running a write tool and sends confirm=true', async () => {
    api.executeMcpTool.mockResolvedValue({ result: 'ok' });
    render(<McpToolTryIt tool={writeTool} />);
    await userEvent.type(screen.getByLabelText(/process_instance_id/), '7');
    await userEvent.click(screen.getByRole('button', { name: 'Execute' }));
    expect(api.executeMcpTool).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole('button', { name: 'Run it' }));
    expect(api.executeMcpTool).toHaveBeenCalledWith('cancel_process_instance', { process_instance_id: 7 }, true);
  });

  it('shows the backend reason when the call fails', async () => {
    api.executeMcpTool.mockRejectedValue(
      new ApiError('/v1.0/m8flow/mcp-tools/execute', 502, 'POST', "Tool 'get_process_instance' reported an error."),
    );
    render(<McpToolTryIt tool={readTool} />);
    await userEvent.type(screen.getByLabelText(/process_instance_id/), '7');
    await userEvent.click(screen.getByRole('button', { name: 'Execute' }));
    expect(await screen.findByText("Tool 'get_process_instance' reported an error.")).toBeInTheDocument();
  });
});

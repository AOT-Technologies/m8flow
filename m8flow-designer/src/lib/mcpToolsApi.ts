import { ApiError, apiGet, apiPost } from './api';

/**
 * Admin MCP tools catalog (M8F-404, restored for next-gen in M8F-539). Shapes mirror
 * `mcp_tools_controller.py`; the backend's `/m8flow/mcp-tools*` grants are the
 * enforcement layer.
 */
const BASE_PATH = '/v1.0/m8flow/mcp-tools';

export type McpToolParameter = {
  name: string;
  /** JSON-Schema type: string | integer | number | boolean | object | array | any. */
  type: string;
  required: boolean;
  description: string;
};

export type McpTool = {
  name: string;
  description: string;
  category: string;
  /** "write" also means the backend refuses execution without `confirm: true`. */
  badge: 'read' | 'write';
  parameters: McpToolParameter[];
};

export type McpToolsCatalog = {
  server_url: string;
  protocol_version: string;
  tool_count: number;
  tools: McpTool[];
};

export type McpPing = {
  ok: boolean;
  latency_ms: number;
  protocol_version: string | null;
  /** False only when the MCP server rejected the caller's token. */
  authorized: boolean;
};

export function fetchMcpToolsCatalog(): Promise<McpToolsCatalog> {
  return apiGet<McpToolsCatalog>(BASE_PATH);
}

export function pingMcpServer(): Promise<McpPing> {
  return apiGet<McpPing>(`${BASE_PATH}/ping`);
}

export function executeMcpTool(
  toolName: string,
  args: Record<string, unknown>,
  confirm: boolean,
): Promise<{ result: unknown }> {
  return apiPost<{ result: unknown }>(`${BASE_PATH}/execute`, { tool_name: toolName, arguments: args, confirm });
}

/** The backend's own reason (not configured / not authorized / unreachable) beats a
 * generic line -- hiding it is what made M8F-539 undiagnosable. */
export function mcpErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.serverMessage) return err.serverMessage;
  return fallback;
}

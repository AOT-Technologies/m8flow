import { Cable, Copy, ExternalLink } from 'lucide-react';

import { Card } from '@/components/ui/card';

const MCP_SERVER_URL = import.meta.env.VITE_MCP_SERVER_URL ?? '';

export default function McpConnectionPage() {
  return (
    <main className="flex-1 px-11 py-10" data-testid="mcp-connection-page">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">MCP Connection</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Connect an MCP-compatible client to m8flow using the server URL below.
        </p>
      </div>

      <Card variant="bordered" className="max-w-3xl p-6">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted text-primary">
            <Cable className="size-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold">MCP server</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Use this endpoint in your MCP client configuration.
            </p>
          </div>
        </div>

        {MCP_SERVER_URL ? (
          <div className="mt-6 rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Server URL
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 break-all text-sm text-foreground">
                {MCP_SERVER_URL}
              </code>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted"
                onClick={() => void navigator.clipboard?.writeText(MCP_SERVER_URL)}
              >
                <Copy className="size-3.5" aria-hidden />
                Copy
              </button>
              <a
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted"
                href={MCP_SERVER_URL}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink className="size-3.5" aria-hidden />
                Open
              </a>
            </div>
          </div>
        ) : (
          <p className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            The MCP server URL is not configured for this environment.
          </p>
        )}
      </Card>
    </main>
  );
}

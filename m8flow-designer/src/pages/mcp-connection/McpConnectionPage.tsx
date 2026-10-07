import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Braces, Check, Copy, Globe, Link2, Lock, SquareTerminal } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';

const MCP_SERVER_URL = import.meta.env.VITE_MCP_SERVER_URL ?? '';
const SERVER_NAME = 'm8flow';

// Outline pill used by every client-card action (matches the MCP Connection mockup).
const OUTLINE_ACTION =
  'h-12 w-full gap-2 rounded-full border-nav-active bg-card text-base font-semibold text-nav-active hover:bg-nav-active/10 hover:text-nav-active';

export function claudeCodeCommand(url: string): string {
  return `claude mcp add --transport http ${SERVER_NAME} ${url}`;
}

export function cursorConfig(url: string): string {
  return JSON.stringify({ mcpServers: { [SERVER_NAME]: { url } } }, null, 2);
}

/** Copy to the clipboard; `copied` flips back after a moment, `failed` when the browser refuses. */
function useCopy() {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setFailed(false);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
      setFailed(true);
    }
  }

  return { copied, failed, copy };
}

function CopyButton({ text, label, primary = false }: { text: string; label: string; primary?: boolean }) {
  const { copied, failed, copy } = useCopy();
  const Icon = copied ? Check : Copy;
  return (
    <div className={primary ? 'shrink-0' : 'w-full'}>
      <Button
        type="button"
        variant="outline"
        size="pill"
        onClick={() => void copy(text)}
        className={
          primary
            ? 'h-12 gap-2 rounded-full border-transparent bg-nav-active px-6 text-base font-semibold text-foreground hover:bg-nav-active/85'
            : OUTLINE_ACTION
        }
      >
        <Icon className="size-4" aria-hidden />
        {copied ? 'Copied' : label}
      </Button>
      {failed && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          Copying isn't available here. Select the text to copy it manually.
        </p>
      )}
    </div>
  );
}

function ClientCard({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-xl border border-border p-6">
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground">{icon}</span>
        <h3 className="text-lg font-semibold">{title}</h3>
      </div>
      <p className="mt-5 mb-5 text-sm text-muted-foreground">{description}</p>
      <div className="mt-auto">{children}</div>
    </div>
  );
}

function ClaudeAiSteps({ url }: { url: string }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="pill"
          className={OUTLINE_ACTION}
        >
          View steps
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add m8flow to Claude.ai</DialogTitle>
          <DialogDescription>Add the server as a custom connector.</DialogDescription>
        </DialogHeader>
        <ol className="list-decimal space-y-2 pl-5 text-sm">
          <li>In Claude.ai, open Settings → Connectors.</li>
          <li>Choose Add custom connector.</li>
          <li>
            Name it <span className="font-semibold">{SERVER_NAME}</span> and paste the server URL:
            <code className="mt-1 block break-all rounded-md bg-muted px-2 py-1 font-mono text-xs">{url}</code>
          </li>
          <li>Select Add, then Connect and sign in with your m8flow account.</li>
        </ol>
        <CopyButton text={url} label="Copy server URL" />
      </DialogContent>
    </Dialog>
  );
}

export default function McpConnectionPage() {
  return (
    <main className="flex-1 px-11 py-10" data-testid="mcp-connection-page">
      <Card variant="bordered" className="max-w-5xl p-8">
        <div className="flex items-center gap-5">
          <span className="flex size-14 shrink-0 items-center justify-center rounded-xl bg-nav-active/15 text-nav-active">
            <Link2 className="size-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">MCP Connection</h1>
            <p className="mt-1 text-base text-muted-foreground">Connect AI assistants to your m8flow workspace.</p>
          </div>
        </div>

        {MCP_SERVER_URL ? (
          <>
            <div className="mt-8 rounded-xl border border-border bg-muted/60 p-7">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Server URL</p>
                  <code className="mt-3 block break-all font-mono text-lg text-foreground">{MCP_SERVER_URL}</code>
                </div>
                <CopyButton text={MCP_SERVER_URL} label="Copy" primary />
              </div>
              <p className="mt-4 flex items-center gap-1.5 text-sm text-muted-foreground">
                <Lock className="size-3.5" aria-hidden />
                OAuth sign-in on first connect · tools run with your m8flow permissions
              </p>
            </div>

            <h2 className="mt-8 mb-4 text-lg font-semibold">Set up a client</h2>
            <div className="grid gap-5 md:grid-cols-3">
              <ClientCard
                icon={<SquareTerminal className="size-5" aria-hidden />}
                title="Claude Code"
                description="One command in your terminal"
              >
                <CopyButton text={claudeCodeCommand(MCP_SERVER_URL)} label="Copy command" />
              </ClientCard>
              <ClientCard icon={<Braces className="size-5" aria-hidden />} title="Cursor" description="Paste JSON into mcp.json">
                <CopyButton text={cursorConfig(MCP_SERVER_URL)} label="Copy config" />
              </ClientCard>
              <ClientCard
                icon={<Globe className="size-5" aria-hidden />}
                title="Claude.ai"
                description="Add as a custom connector"
              >
                <ClaudeAiSteps url={MCP_SERVER_URL} />
              </ClientCard>
            </div>
          </>
        ) : (
          <p className="mt-8 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            The MCP server URL is not configured for this environment.
          </p>
        )}
      </Card>
    </main>
  );
}

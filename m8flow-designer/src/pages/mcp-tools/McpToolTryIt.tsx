import { Play } from 'lucide-react';
import { useState } from 'react';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { executeMcpTool, mcpErrorMessage, type McpTool } from '@/lib/mcpToolsApi';

import { buildArguments } from './mcpToolArgs';

export function McpToolTryIt({ tool }: { tool: McpTool }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pendingArgs, setPendingArgs] = useState<Record<string, unknown> | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<unknown>(undefined);
  const [runError, setRunError] = useState<string | null>(null);

  const setValue = (name: string, value: string) => setValues((current) => ({ ...current, [name]: value }));

  const run = (args: Record<string, unknown>, confirm: boolean) => {
    setRunning(true);
    setRunError(null);
    setResult(undefined);
    executeMcpTool(tool.name, args, confirm)
      .then((response) => setResult(response.result))
      .catch((err: unknown) => setRunError(mcpErrorMessage(err, 'Could not run this tool. Please try again.')))
      .finally(() => {
        setRunning(false);
        setPendingArgs(null);
      });
  };

  const onExecute = () => {
    const built = buildArguments(tool.parameters, values);
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    // The backend refuses a write without confirm=true; this dialog is the UX for that gate.
    if (tool.badge === 'write') {
      setPendingArgs(built.args);
    } else {
      run(built.args, false);
    }
  };

  return (
    <div className="mt-4 space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Try it</h3>
      {tool.parameters.map((param) => {
        const id = `${tool.name}-${param.name}`;
        return (
          <div key={param.name} className="space-y-1">
            <label htmlFor={id} className="text-sm font-medium">
              {param.name}
              {param.required && <span className="text-destructive"> *</span>}
              <span className="ml-2 font-normal text-muted-foreground">{param.type}</span>
            </label>
            {param.type === 'boolean' ? (
              <select
                id={id}
                value={values[param.name] ?? ''}
                onChange={(event) => setValue(param.name, event.target.value)}
                className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm"
              >
                <option value="">—</option>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : (
              <Input
                id={id}
                value={values[param.name] ?? ''}
                placeholder={param.type === 'object' || param.type === 'array' ? 'JSON' : undefined}
                aria-invalid={Boolean(errors[param.name])}
                onChange={(event) => setValue(param.name, event.target.value)}
              />
            )}
            {errors[param.name] && <p className="text-xs text-destructive">{errors[param.name]}</p>}
          </div>
        );
      })}
      <Button onClick={onExecute} disabled={running}>
        <Play aria-hidden />
        {running ? 'Running…' : 'Execute'}
      </Button>
      {runError && <Alert tone="error">{runError}</Alert>}
      {result !== undefined && (
        <pre className="max-h-96 overflow-auto rounded-lg bg-muted p-3 text-xs" data-testid="mcp-tool-result">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
      <ConfirmDialog
        open={pendingArgs !== null}
        onOpenChange={(open) => {
          if (!open) setPendingArgs(null);
        }}
        title={`Run ${tool.name}?`}
        description="This tool performs a write operation on real data."
        confirmLabel="Run it"
        tone="destructive"
        pending={running}
        onConfirm={() => {
          if (pendingArgs) run(pendingArgs, true);
        }}
      />
    </div>
  );
}

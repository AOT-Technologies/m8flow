import { useState } from 'react';
import { ChevronLeft, ChevronRight, Play } from 'lucide-react';

import type { ScriptUnitTestRunResult } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

import { newScriptUnitTestId, parseJsonObject, type ScriptUnitTestCase } from '../scriptUnitTests';

export type ScriptUnitTestsPanelProps = {
  pythonScript: string;
  cases: ScriptUnitTestCase[];
  onCasesChange: (cases: ScriptUnitTestCase[]) => void;
  onRun: (input: {
    python_script: string;
    input_json: Record<string, unknown>;
    expected_output_json: Record<string, unknown>;
  }) => Promise<ScriptUnitTestRunResult>;
};

export function ScriptUnitTestsPanel({
  pythonScript,
  cases,
  onCasesChange,
  onRun,
}: ScriptUnitTestsPanelProps) {
  const [index, setIndex] = useState(0);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ScriptUnitTestRunResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const current = cases[index];

  const updateCurrent = (patch: Partial<ScriptUnitTestCase>) => {
    if (!current) return;
    onCasesChange(cases.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    setResult(null);
    setRunError(null);
  };

  const handleCreate = () => {
    const next: ScriptUnitTestCase = {
      id: newScriptUnitTestId(),
      inputJson: '{}',
      expectedOutputJson: '{}',
    };
    onCasesChange([...cases, next]);
    setIndex(cases.length);
    setResult(null);
    setRunError(null);
  };

  const handleRun = async () => {
    if (!current) return;
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      const outcome = await onRun({
        python_script: pythonScript,
        input_json: parseJsonObject(current.inputJson, 'Input JSON'),
        expected_output_json: parseJsonObject(current.expectedOutputJson, 'Expected output JSON'),
      });
      setResult(outcome);
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : 'Failed to run script unit test');
    } finally {
      setRunning(false);
    }
  };

  if (!current) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-5">
        <p className="text-sm text-muted-foreground">No unit tests on this script task yet.</p>
        <Button type="button" variant="pill-outline" size="pill" onClick={handleCreate}>
          Create unit test
        </Button>
      </div>
    );
  }

  const passed = result?.result === true;
  const failed = result != null && result.result === false;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex flex-none flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-2">
        <p className="font-mono text-xs text-foreground">{current.id}</p>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={index <= 0}
            onClick={() => {
              setIndex((i) => i - 1);
              setResult(null);
              setRunError(null);
            }}
            aria-label="Previous unit test"
          >
            <ChevronLeft className="size-4" strokeWidth={2} />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={index >= cases.length - 1}
            onClick={() => {
              setIndex((i) => i + 1);
              setResult(null);
              setRunError(null);
            }}
            aria-label="Next unit test"
          >
            <ChevronRight className="size-4" strokeWidth={2} />
          </Button>
          <Button
            type="button"
            variant="pill-outline"
            size="pill"
            className="px-3 py-1 text-xs"
            disabled={running}
            onClick={() => void handleRun()}
          >
            <Play className="size-3.5" strokeWidth={2} />
            {running ? 'Running…' : 'Run'}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={handleCreate}>
            Add test
          </Button>
        </div>
      </div>

      {runError ? (
        <p className="flex-none px-5 py-2 text-sm text-destructive" role="alert">
          {runError}
        </p>
      ) : null}
      {passed ? (
        <p className="flex-none px-5 py-2 text-sm text-foreground" role="status">
          Passed.
        </p>
      ) : null}
      {failed ? (
        <p className="flex-none px-5 py-2 text-sm text-destructive" role="alert">
          {result?.error || 'Failed.'}
        </p>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-2 gap-3 overflow-hidden p-5">
        <label className="flex min-h-0 flex-col gap-1.5 text-xs font-medium text-muted-foreground">
          Input JSON
          <Textarea
            value={current.inputJson}
            onChange={(event) => updateCurrent({ inputJson: event.target.value })}
            aria-label="Input JSON"
            className="min-h-0 flex-1 font-mono text-sm"
          />
        </label>
        <label className="flex min-h-0 flex-col gap-1.5 text-xs font-medium text-muted-foreground">
          Expected output JSON
          <Textarea
            value={current.expectedOutputJson}
            onChange={(event) => updateCurrent({ expectedOutputJson: event.target.value })}
            aria-label="Expected output JSON"
            className="min-h-0 flex-1 font-mono text-sm"
          />
        </label>
      </div>
    </div>
  );
}

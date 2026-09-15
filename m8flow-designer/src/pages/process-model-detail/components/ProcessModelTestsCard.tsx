import { useEffect, useState, type FormEvent } from 'react';

import type {
  ProcessModelTestRunResult,
  ScriptUnitTest,
  ScriptUnitTestRunResult,
} from '@/lib/api';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

const inertBtn = 'cursor-default select-none disabled:cursor-default disabled:opacity-100';

export function parseJsonObject(raw: string, label: string): Record<string, unknown> {
  const trimmed = raw.trim() || '{}';
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${label} must be valid JSON`);
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return parsed as Record<string, unknown>;
}

export type ProcessModelTestsCardProps = {
  canManage?: boolean;
  hasBpmnTests: boolean;
  onRunBpmnTests?: () => Promise<ProcessModelTestRunResult>;
  onFetchScriptUnitTests?: () => Promise<ScriptUnitTest[]>;
  onCreateScriptUnitTest?: (input: {
    bpmn_task_identifier: string;
    input_json: Record<string, unknown>;
    expected_output_json: Record<string, unknown>;
  }) => Promise<{ id: string }>;
  onRunScriptUnitTest?: (input: { unit_test_id: string }) => Promise<ScriptUnitTestRunResult>;
};

export function ProcessModelTestsCard({
  canManage = false,
  hasBpmnTests,
  onRunBpmnTests,
  onFetchScriptUnitTests,
  onCreateScriptUnitTest,
  onRunScriptUnitTest,
}: ProcessModelTestsCardProps) {
  const [bpmnRunning, setBpmnRunning] = useState(false);
  const [bpmnError, setBpmnError] = useState<string | null>(null);
  const [bpmnResult, setBpmnResult] = useState<ProcessModelTestRunResult | null>(null);
  const [scriptTests, setScriptTests] = useState<ScriptUnitTest[]>([]);
  const [scriptLoadError, setScriptLoadError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [taskId, setTaskId] = useState('');
  const [inputJson, setInputJson] = useState('{}');
  const [expectedJson, setExpectedJson] = useState('{}');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [scriptRun, setScriptRun] = useState<{ id: string; result: ScriptUnitTestRunResult } | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);

  useEffect(() => {
    if (!canManage || !onFetchScriptUnitTests) {
      setScriptTests([]);
      return;
    }
    let cancelled = false;
    onFetchScriptUnitTests()
      .then((rows) => {
        if (!cancelled) {
          setScriptTests(rows);
          setScriptLoadError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setScriptLoadError(err instanceof Error ? err.message : 'Failed to load script unit tests');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canManage, onFetchScriptUnitTests]);

  const bpmnLive = Boolean(canManage && hasBpmnTests && onRunBpmnTests);
  const scriptLive = Boolean(canManage && onCreateScriptUnitTest);

  return (
    <Card id="tests" variant="bordered" className="mb-[22px]">
      <div className="px-[22px] pt-4 pb-5">
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-foreground">Tests</h2>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">
              BPMN unit tests (test_*.json) and script-task unit tests
            </p>
          </div>
          {bpmnLive ? (
            <Button
              type="button"
              variant="pill-outline"
              size="pill"
              className="px-3.5 py-1.5 text-xs"
              disabled={bpmnRunning}
              onClick={async () => {
                if (!onRunBpmnTests) return;
                setBpmnRunning(true);
                setBpmnError(null);
                try {
                  setBpmnResult(await onRunBpmnTests());
                } catch (err: unknown) {
                  setBpmnResult(null);
                  setBpmnError(err instanceof Error ? err.message : 'Failed to run BPMN tests');
                } finally {
                  setBpmnRunning(false);
                }
              }}
            >
              {bpmnRunning ? 'Running…' : 'Run BPMN tests'}
            </Button>
          ) : (
            <Button
              type="button"
              disabled
              variant="pill-outline"
              size="pill"
              className={`${inertBtn} px-3.5 py-1.5 text-xs`}
            >
              Run BPMN tests
            </Button>
          )}
        </div>
        {bpmnError ? (
          <p className="mb-3 text-sm text-destructive" role="alert">
            {bpmnError}
          </p>
        ) : null}

        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-[13px] font-semibold text-foreground">Script unit tests</h3>
          {scriptLive ? (
            <Button
              type="button"
              variant="pill-outline"
              size="pill"
              className="px-3.5 py-1.5 text-xs"
              onClick={() => {
                setCreateError(null);
                setTaskId('');
                setInputJson('{}');
                setExpectedJson('{}');
                setCreateOpen(true);
              }}
            >
              Create script unit test
            </Button>
          ) : (
            <Button
              type="button"
              disabled
              variant="pill-outline"
              size="pill"
              className={`${inertBtn} px-3.5 py-1.5 text-xs`}
            >
              Create script unit test
            </Button>
          )}
        </div>
        {scriptLoadError ? (
          <p className="text-sm text-destructive" role="alert">
            {scriptLoadError}
          </p>
        ) : scriptTests.length === 0 ? (
          <p className="rounded-xl border border-border px-4 py-6 text-center text-[13.5px] text-muted-foreground">
            No script unit tests yet.
          </p>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border">
            {scriptTests.map((row) => (
              <div
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2.5 first:border-t-0"
              >
                <div className="min-w-0">
                  <div className="font-mono text-[13px] text-foreground">{row.id}</div>
                  <div className="text-[12px] text-muted-foreground">{row.bpmn_task_identifier}</div>
                </div>
                {canManage && onRunScriptUnitTest ? (
                  <Button
                    type="button"
                    variant="pill-outline"
                    size="pill"
                    className="px-3 py-1 text-xs"
                    disabled={runningId === row.id}
                    onClick={async () => {
                      setRunningId(row.id);
                      try {
                        const result = await onRunScriptUnitTest({ unit_test_id: row.id });
                        setScriptRun({ id: row.id, result });
                      } catch (err: unknown) {
                        setScriptRun({
                          id: row.id,
                          result: {
                            result: false,
                            error: err instanceof Error ? err.message : 'Failed to run script unit test',
                          },
                        });
                      } finally {
                        setRunningId(null);
                      }
                    }}
                  >
                    {runningId === row.id ? 'Running…' : 'Run'}
                  </Button>
                ) : (
                  <Button
                    type="button"
                    disabled
                    variant="pill-outline"
                    size="pill"
                    className={`${inertBtn} px-3 py-1 text-xs`}
                  >
                    Run
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal
        open={bpmnResult != null}
        onOpenChange={(next) => { if (!next) setBpmnResult(null); }}
        title="BPMN test results"
        footer={
          <Button type="button" onClick={() => setBpmnResult(null)}>
            Close
          </Button>
        }
      >
        <p className="-mt-1 text-sm text-muted-foreground">
          {bpmnResult?.all_passed
            ? `All ${bpmnResult.passing.length} test${bpmnResult.passing.length === 1 ? '' : 's'} passed.`
            : `${bpmnResult?.failing.length ?? 0} failed, ${bpmnResult?.passing.length ?? 0} passed.`}
        </p>
        {bpmnResult?.failing.length ? (
          <ul className="list-disc pl-5 text-sm text-foreground">
            {bpmnResult.failing.slice(0, 8).map((row) => (
              <li key={`${row.bpmn_file}:${row.test_case_identifier}`}>
                {row.test_case_identifier}
                {row.test_case_error_details?.error_messages?.[0]
                  ? ` — ${row.test_case_error_details.error_messages[0]}`
                  : ''}
              </li>
            ))}
          </ul>
        ) : null}
      </Modal>

      <Modal
        open={scriptRun != null}
        onOpenChange={(next) => { if (!next) setScriptRun(null); }}
        title="Script unit test"
        footer={
          <Button type="button" onClick={() => setScriptRun(null)}>
            Close
          </Button>
        }
      >
        <p className="-mt-1 text-sm text-muted-foreground">
          {scriptRun?.result.result ? 'Passed.' : scriptRun?.result.error || 'Failed.'}
        </p>
      </Modal>

      {onCreateScriptUnitTest ? (
        <Modal
          open={createOpen}
          onOpenChange={(next) => { if (!next) setCreateOpen(false); }}
          title="Create script unit test"
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>
                Cancel
              </Button>
              <Button type="submit" form="create-script-unit-test-form" disabled={creating || !taskId.trim()}>
                {creating ? 'Creating…' : 'Create'}
              </Button>
            </>
          }
        >
          <p className="-mt-1 text-sm text-muted-foreground">
            Stores the case on a script task in the primary BPMN file.
          </p>
          <form
            id="create-script-unit-test-form"
            className="flex flex-col gap-4"
            onSubmit={async (event: FormEvent) => {
              event.preventDefault();
              if (!onCreateScriptUnitTest) return;
              setCreating(true);
              setCreateError(null);
              try {
                const created = await onCreateScriptUnitTest({
                  bpmn_task_identifier: taskId.trim(),
                  input_json: parseJsonObject(inputJson, 'Input JSON'),
                  expected_output_json: parseJsonObject(expectedJson, 'Expected output JSON'),
                });
                setScriptTests((prev) => [
                  ...prev,
                  { id: created.id, bpmn_task_identifier: taskId.trim() },
                ]);
                setCreateOpen(false);
              } catch (err: unknown) {
                setCreateError(err instanceof Error ? err.message : 'Failed to create script unit test');
              } finally {
                setCreating(false);
              }
            }}
            noValidate
          >
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              Script task ID
              <Input
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
                aria-label="Script task ID"
                placeholder="Script_1"
                required
              />
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              Input JSON
              <Textarea
                value={inputJson}
                onChange={(e) => setInputJson(e.target.value)}
                aria-label="Input JSON"
                className="font-mono text-sm"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              Expected output JSON
              <Textarea
                value={expectedJson}
                onChange={(e) => setExpectedJson(e.target.value)}
                aria-label="Expected output JSON"
                className="font-mono text-sm"
              />
            </label>
            {createError ? (
              <p className="text-sm text-destructive" role="alert">
                {createError}
              </p>
            ) : null}
          </form>
        </Modal>
      ) : null}
    </Card>
  );
}

import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import i18n from '@/i18n';

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
    throw new Error(i18n.t('processModelDetail.tests.invalidJson', { label }));
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(i18n.t('processModelDetail.tests.notJsonObject', { label }));
  }
  return parsed as Record<string, unknown>;
}

export type ProcessModelTestsCardProps = {
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
  hasBpmnTests,
  onRunBpmnTests,
  onFetchScriptUnitTests,
  onCreateScriptUnitTest,
  onRunScriptUnitTest,
}: ProcessModelTestsCardProps) {
  const { t } = useTranslation();
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
    if (!onFetchScriptUnitTests) {
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
          setScriptLoadError(err instanceof Error ? err.message : i18n.t('processModelDetail.tests.loadScriptFailed'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [onFetchScriptUnitTests]);

  const bpmnLive = Boolean(hasBpmnTests && onRunBpmnTests);
  const scriptLive = Boolean(onCreateScriptUnitTest);

  return (
    <Card id="tests" variant="bordered" className="mb-[22px]">
      <div className="px-[22px] pt-4 pb-5">
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-foreground">{t('processModelDetail.tests.title')}</h2>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">
              {t('processModelDetail.tests.subtitle')}
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
                  setBpmnError(err instanceof Error ? err.message : t('processModelDetail.tests.runBpmnFailed'));
                } finally {
                  setBpmnRunning(false);
                }
              }}
            >
              {bpmnRunning ? t('processModelDetail.tests.running') : t('processModelDetail.tests.runBpmnTests')}
            </Button>
          ) : (
            <Button
              type="button"
              disabled
              variant="pill-outline"
              size="pill"
              className={`${inertBtn} px-3.5 py-1.5 text-xs`}
            >
              {t('processModelDetail.tests.runBpmnTests')}
            </Button>
          )}
        </div>
        {bpmnError ? (
          <p className="mb-3 text-sm text-destructive" role="alert">
            {bpmnError}
          </p>
        ) : null}

        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-[13px] font-semibold text-foreground">{t('processModelDetail.tests.scriptUnitTests')}</h3>
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
              {t('processModelDetail.tests.createScriptUnitTest')}
            </Button>
          ) : (
            <Button
              type="button"
              disabled
              variant="pill-outline"
              size="pill"
              className={`${inertBtn} px-3.5 py-1.5 text-xs`}
            >
              {t('processModelDetail.tests.createScriptUnitTest')}
            </Button>
          )}
        </div>
        {scriptLoadError ? (
          <p className="text-sm text-destructive" role="alert">
            {scriptLoadError}
          </p>
        ) : scriptTests.length === 0 ? (
          <p className="rounded-xl border border-border px-4 py-6 text-center text-[13.5px] text-muted-foreground">
            {t('processModelDetail.tests.noScriptUnitTests')}
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
                {onRunScriptUnitTest ? (
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
                            error: err instanceof Error ? err.message : t('processModelDetail.tests.runScriptFailed'),
                          },
                        });
                      } finally {
                        setRunningId(null);
                      }
                    }}
                  >
                    {runningId === row.id ? t('processModelDetail.tests.running') : t('processModelDetail.tests.run')}
                  </Button>
                ) : (
                  <Button
                    type="button"
                    disabled
                    variant="pill-outline"
                    size="pill"
                    className={`${inertBtn} px-3 py-1 text-xs`}
                  >
                    {t('processModelDetail.tests.run')}
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
        title={t('processModelDetail.tests.bpmnResultsTitle')}
        footer={
          <Button type="button" onClick={() => setBpmnResult(null)}>
            {t('common.close')}
          </Button>
        }
      >
        <p className="-mt-1 text-sm text-muted-foreground">
          {bpmnResult?.all_passed
            ? t('processModelDetail.tests.allPassed', { count: bpmnResult.passing.length })
            : t('processModelDetail.tests.summary', {
                failed: bpmnResult?.failing.length ?? 0,
                passed: bpmnResult?.passing.length ?? 0,
              })}
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
        title={t('processModelDetail.tests.scriptUnitTest')}
        footer={
          <Button type="button" onClick={() => setScriptRun(null)}>
            {t('common.close')}
          </Button>
        }
      >
        <p className="-mt-1 text-sm text-muted-foreground">
          {scriptRun?.result.result
            ? t('processModelDetail.tests.passed')
            : scriptRun?.result.error || t('processModelDetail.tests.failed')}
        </p>
      </Modal>

      {onCreateScriptUnitTest ? (
        <Modal
          open={createOpen}
          onOpenChange={(next) => { if (!next) setCreateOpen(false); }}
          title={t('processModelDetail.tests.createScriptUnitTest')}
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" form="create-script-unit-test-form" disabled={creating || !taskId.trim()}>
                {creating ? t('processModelDetail.creating') : t('processModelDetail.tests.create')}
              </Button>
            </>
          }
        >
          <p className="-mt-1 text-sm text-muted-foreground">
            {t('processModelDetail.tests.createHint')}
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
                  input_json: parseJsonObject(inputJson, t('processModelDetail.tests.inputJson')),
                  expected_output_json: parseJsonObject(expectedJson, t('processModelDetail.tests.expectedOutputJson')),
                });
                setScriptTests((prev) => [
                  ...prev,
                  { id: created.id, bpmn_task_identifier: taskId.trim() },
                ]);
                setCreateOpen(false);
              } catch (err: unknown) {
                setCreateError(err instanceof Error ? err.message : t('processModelDetail.tests.createFailed'));
              } finally {
                setCreating(false);
              }
            }}
            noValidate
          >
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              {t('processModelDetail.tests.scriptTaskId')}
              <Input
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
                aria-label={t('processModelDetail.tests.scriptTaskId')}
                placeholder="Script_1"
                required
              />
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              {t('processModelDetail.tests.inputJson')}
              <Textarea
                value={inputJson}
                onChange={(e) => setInputJson(e.target.value)}
                aria-label={t('processModelDetail.tests.inputJson')}
                className="font-mono text-sm"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
              {t('processModelDetail.tests.expectedOutputJson')}
              <Textarea
                value={expectedJson}
                onChange={(e) => setExpectedJson(e.target.value)}
                aria-label={t('processModelDetail.tests.expectedOutputJson')}
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

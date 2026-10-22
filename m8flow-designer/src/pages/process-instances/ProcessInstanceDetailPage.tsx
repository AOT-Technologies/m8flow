import { lazy, Suspense, type ReactNode, useCallback, useEffect, useState } from 'react';
import { Link2, Pause, Play, Square, Trash2 } from 'lucide-react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import type { ParseKeys } from 'i18next';
import { Trans, useTranslation } from 'react-i18next';

import i18n, { literalTransValues } from '@/i18n';
import { ApiError } from '@/lib/api';
import {
  deleteProcessInstance,
  fetchProcessInstanceDetail,
  postProcessInstanceLifecycle,
  type ProcessInstanceDetail,
  type ProcessInstanceLifecycleAction,
  type ProcessInstanceTaskState,
} from '@/lib/processInstancesApi';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { Alert } from '@/components/library/alert/Alert';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { EmptyState } from '@/components/library/empty-state/EmptyState';
import { Pill } from '@/components/library/pill/Pill';
import { processInstanceStatusToPillProps } from '@/components/library/pill/processInstanceStatusToPillProps';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { processInstanceLifecycleVisibility } from './lifecycleActions';
import { ProcessInstanceCompletableTasksTable } from './components/ProcessInstanceCompletableTasksTable';
import { ProcessInstanceCompletedTasksTable } from './components/ProcessInstanceCompletedTasksTable';
import { ProcessInstanceEventsTable } from './components/ProcessInstanceEventsTable';
import { ProcessInstanceMilestonesTable } from './components/ProcessInstanceMilestonesTable';
import { ProcessInstanceTaskModal } from './components/ProcessInstanceTaskModal';
import { latestTaskForElement } from './taskSelection';

const InstanceDiagramViewer = lazy(() =>
  import('./components/InstanceDiagramViewer').then((m) => ({ default: m.InstanceDiagramViewer })),
);

type DetailTab = 'diagram' | 'milestones' | 'events' | 'messages' | 'tasks';

const TABS: { id: DetailTab; labelKey: ParseKeys }[] = [
  { id: 'diagram', labelKey: 'processInstances.detail.tabs.diagram' },
  { id: 'milestones', labelKey: 'processInstances.detail.tabs.milestones' },
  { id: 'events', labelKey: 'processInstances.detail.tabs.events' },
  { id: 'messages', labelKey: 'processInstances.detail.tabs.messages' },
  { id: 'tasks', labelKey: 'processInstances.detail.tabs.tasks' },
];

function formatUtcTimestamp(timestamp: string | null | undefined): string {
  if (timestamp == null) {
    return '—';
  }
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) {
    return '—';
  }
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

function IconAction({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size="icon-lg"
      className="rounded-full"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </Button>
  );
}

function MetaCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2.5 text-[13.5px]">
      <span className="w-[90px] shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

/** Adapter passed to `Breadcrumbs`' `LinkComponent` for client-side
 * navigation (component-adoption map, ticket 06). */
function RouterBreadcrumbLink({ href, className, children }: BreadcrumbLinkProps) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

/**
 * Process instance detail — mockup shell: breadcrumb, title + icon
 * actions, metadata grid, Open tasks, tab bodies. Download is
 * gone. Copy link is the current URL. Updated / Last milestone come from
 * the designer GET; Revision stays `—` (no git, no hash, no GET key).
 */
export default function ProcessInstanceDetailPage() {
  const { t } = useTranslation();
  const { instanceId: instanceIdParam } = useParams<{ instanceId: string }>();
  const navigate = useNavigate();
  const { scopedTenantId, needsTenantForWrite } = useActiveTenant();
  const {
    canSuspendProcessInstances,
    canResumeProcessInstances,
    canTerminateProcessInstances,
    canDeleteProcessInstances,
  } = useCapabilities();
  // Reads work under All Tenants; lifecycle actions are writes and must land
  // in exactly one tenant, so they stay disabled until a tenant is selected.
  const canSuspend = canSuspendProcessInstances && !needsTenantForWrite;
  const canResume = canResumeProcessInstances && !needsTenantForWrite;
  const canTerminate = canTerminateProcessInstances && !needsTenantForWrite;

  const parsedId = Number.isFinite(Number(instanceIdParam)) ? Number(instanceIdParam) : NaN;
  const validId = Number.isFinite(parsedId);

  const [detail, setDetail] = useState<ProcessInstanceDetail | null>(null);
  const [loading, setLoading] = useState(validId);
  const [notFound, setNotFound] = useState(!validId);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [confirmingTerminate, setConfirmingTerminate] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [tab, setTab] = useState<DetailTab>('diagram');
  const [searchParams] = useSearchParams();
  const toTaskGuid = searchParams.get('to_task_guid');
  const [selectedTask, setSelectedTask] = useState<ProcessInstanceTaskState | null>(null);

  // A timestamp link in the Events tab lands here with ?to_task_guid= —
  // show the diagram, which is what that view changes.
  useEffect(() => {
    if (toTaskGuid) setTab('diagram');
  }, [toTaskGuid]);

  const handleElementClick = useCallback(
    (bpmnIdentifier: string) => {
      const task = latestTaskForElement(detail?.tasks ?? [], bpmnIdentifier);
      if (task) setSelectedTask(task);
    },
    [detail],
  );

  useEffect(() => {
    if (!validId) {
      setDetail(null);
      setLoading(false);
      setNotFound(true);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);

    fetchProcessInstanceDetail(parsedId, scopedTenantId, toTaskGuid)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDetail(null);
        // As of a task, a 404 is about the task: show it with the way back.
        if (err instanceof ApiError && err.status === 404 && !toTaskGuid) {
          setNotFound(true);
        } else {
          setError(err instanceof Error ? err.message : i18n.t('processInstances.detail.loadError'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [parsedId, validId, scopedTenantId, toTaskGuid]);

  async function handleCopyLink() {
    try {
      await navigator.clipboard?.writeText(window.location.href);
    } catch {
      /* clipboard can reject in insecure contexts */
    }
  }

  async function handleLifecycle(action: ProcessInstanceLifecycleAction) {
    if (!validId || actionBusy) return;
    setActionBusy(true);
    setError(null);
    try {
      await postProcessInstanceLifecycle(parsedId, action, scopedTenantId);
      const next = await fetchProcessInstanceDetail(parsedId, scopedTenantId, toTaskGuid);
      setDetail(next);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('processInstances.detail.updateError'));
    } finally {
      setActionBusy(false);
    }
  }

  async function handleDelete() {
    if (!validId || actionBusy) return;
    setActionBusy(true);
    setError(null);
    try {
      await deleteProcessInstance(parsedId, scopedTenantId);
      navigate('/process-instances', { replace: true });
    } catch (err: unknown) {
      setConfirmingDelete(false);
      setError(err instanceof Error ? err.message : 'Failed to delete process instance');
    } finally {
      setActionBusy(false);
    }
  }

  const timeTravelTarget = toTaskGuid ? detail?.tasks.find((task) => task.guid === toTaskGuid) ?? null : null;

  const statusActions = detail ? processInstanceLifecycleVisibility(detail.status) : null;
  const actions = statusActions ? {
    terminate: statusActions.terminate && canTerminate,
    suspend: statusActions.suspend && canSuspend,
    resume: statusActions.resume && canResume,
  } : null;
  const canDelete = Boolean(
    detail
      && ['complete', 'error', 'terminated'].includes(detail.status)
      && canDeleteProcessInstances
      && !needsTenantForWrite
      && !toTaskGuid,
  );

  return (
    <div className="flex min-h-screen flex-1 flex-col px-11 py-7">
      <Breadcrumbs
        className="mb-[18px] min-w-0 text-[13.5px] text-muted-foreground"
        LinkComponent={RouterBreadcrumbLink}
        linkClassName="shrink-0 text-info font-semibold"
        lastClassName="min-w-0 truncate font-mono"
        items={[
          { label: t('processInstances.title'), href: '/process-instances' },
          { label: `${detail?.process_model_display_name ?? instanceIdParam} #${instanceIdParam}` },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-center gap-4">
        <h1 className="m-0 font-display text-[clamp(24px,2.4vw,32px)] font-semibold tracking-tight text-foreground">
          {t('processInstances.detail.heading', { id: instanceIdParam })}
        </h1>
        <div className="flex items-center gap-2">
          <IconAction label={t('processInstances.copyLink')} onClick={handleCopyLink}>
            <Link2 className="size-4 text-muted-foreground" strokeWidth={1.8} />
          </IconAction>
          {canDelete ? (
            <IconAction
              label="Delete process instance"
              onClick={() => setConfirmingDelete(true)}
              disabled={actionBusy}
            >
              <Trash2 className="size-4 text-destructive" strokeWidth={1.8} />
            </IconAction>
          ) : null}
          {actions?.terminate ? (
            <IconAction
              label={t('processInstances.detail.actions.terminate')}
              onClick={() => setConfirmingTerminate(true)}
              disabled={actionBusy}
            >
              <Square className="size-3.5 fill-destructive text-destructive" strokeWidth={0} />
            </IconAction>
          ) : null}
          {actions?.suspend ? (
            <IconAction
              label={t('processInstances.detail.actions.suspend')}
              onClick={() => handleLifecycle('suspend')}
              disabled={actionBusy}
            >
              <Pause className="size-3.5 fill-muted-foreground text-muted-foreground" strokeWidth={0} />
            </IconAction>
          ) : null}
          {actions?.resume ? (
            <IconAction
              label={t('processInstances.detail.actions.resume')}
              onClick={() => handleLifecycle('resume')}
              disabled={actionBusy}
            >
              <Play className="size-3.5 fill-muted-foreground text-muted-foreground" strokeWidth={0} />
            </IconAction>
          ) : null}
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground" aria-busy="true">
          {t('processInstances.detail.loading')}
        </p>
      ) : notFound ? (
        <p className="text-sm text-muted-foreground" role="status">
          {t('processInstances.detail.notFound')}
        </p>
      ) : error && !detail ? (
        <Alert tone="error">
          {error}
          {toTaskGuid ? (
            <>
              {' '}
              <Link to={`/process-instances/${instanceIdParam}`} className="font-semibold text-info hover:underline">
                {t('processInstances.detail.viewCurrentState')}
              </Link>
            </>
          ) : null}
        </Alert>
      ) : detail ? (
        <>
          {error ? (
            <Alert tone="error" className="mb-4">
              {error}
            </Alert>
          ) : null}

          {detail.status === 'error' ? (
            <Alert tone="error" className="mb-4">
              <strong className="mr-1">{t('processInstances.detail.processError')}</strong>
              <span>
                {t('processInstances.detail.processErrorBody')}
                {detail.error_message ? ` ${detail.error_message}` : ''}
              </span>
            </Alert>
          ) : null}

          {toTaskGuid ? (
            <Alert tone="info" className="mb-4">
              <span>
                <Trans
                  {...literalTransValues}
                  i18nKey="processInstances.detail.timeTravelNotice"
                  values={{
                    task: timeTravelTarget
                      ? timeTravelTarget.bpmn_name || timeTravelTarget.bpmn_identifier
                      : toTaskGuid,
                  }}
                  components={{ strong: <strong /> }}
                />{' '}
                <Link to={`/process-instances/${instanceIdParam}`} className="font-semibold text-info hover:underline">
                  {t('processInstances.detail.viewCurrentState')}
                </Link>
              </span>
            </Alert>
          ) : null}

          <Card variant="bordered" className="mb-[26px] grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-x-7 gap-y-3.5 px-[22px] py-[18px]">
            <MetaCell label={t('common.status')}>
              <Pill {...processInstanceStatusToPillProps(detail.status)} />
            </MetaCell>
            <MetaCell label={t('processInstances.fields.startedBy')}>{detail.started_by || '—'}</MetaCell>
            <MetaCell label={t('processInstances.fields.started')}>
              <span className="font-mono text-[12.5px]">{formatUtcTimestamp(detail.started_at)}</span>
            </MetaCell>
            <MetaCell label={t('processInstances.detail.meta.updated')}>
              <span className="font-mono text-[12.5px]">{formatUtcTimestamp(detail.updated_at)}</span>
            </MetaCell>
            <MetaCell label={t('processInstances.detail.meta.lastMilestone')}>
              {detail.last_milestone_bpmn_name?.trim() || '—'}
            </MetaCell>
            <MetaCell label={t('processInstances.detail.meta.revision')}>
              <span className="font-mono text-xs text-muted-foreground">—</span>
            </MetaCell>
          </Card>

          <div className="mb-7">
            <ProcessInstanceCompletableTasksTable instanceId={parsedId} tenantId={scopedTenantId} />
          </div>

          <Tabs value={tab} onValueChange={(value) => setTab(value as DetailTab)} className="mb-5">
            <TabsList className="gap-[26px]">
              {TABS.map((item) => (
                <TabsTrigger
                  key={item.id}
                  value={item.id}
                  className="text-[14.5px] data-[state=active]:border-info data-[state=active]:text-info"
                >
                  {t(item.labelKey)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {tab === 'diagram' ? (
            detail.bpmn_xml ? (
              <Card variant="bordered" className="relative h-[520px] overflow-hidden">
                <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">{t('processInstances.detail.loadingDiagram')}</p>}>
                  <InstanceDiagramViewer xml={detail.bpmn_xml} tasks={detail.tasks} onElementClick={handleElementClick} />
                </Suspense>
              </Card>
            ) : (
              <EmptyState
                role="status"
                title={t('processInstances.detail.noDiagram')}
              />
            )
          ) : null}

          {tab === 'milestones' ? (
            <ProcessInstanceMilestonesTable instanceId={parsedId} tenantId={scopedTenantId} />
          ) : null}

          {tab === 'events' ? (
            <ProcessInstanceEventsTable instanceId={parsedId} tenantId={scopedTenantId} />
          ) : null}

          {tab === 'messages' ? (
            <EmptyState title={t('processInstances.detail.noMessages')} />
          ) : null}

          {tab === 'tasks' ? (
            <ProcessInstanceCompletedTasksTable instanceId={parsedId} tenantId={scopedTenantId} />
          ) : null}
        </>
      ) : null}

      <ProcessInstanceTaskModal
        instanceId={parsedId}
        tenantId={scopedTenantId}
        task={selectedTask}
        onClose={() => setSelectedTask(null)}
      />

      <ConfirmDialog
        open={confirmingTerminate}
        onOpenChange={setConfirmingTerminate}
        title={t('processInstances.detail.terminateConfirm.title')}
        description={t('processInstances.detail.terminateConfirm.description')}
        confirmLabel={t('processInstances.detail.actions.terminate')}
        onConfirm={() => {
          setConfirmingTerminate(false);
          void handleLifecycle('terminate');
        }}
      />
      <ConfirmDialog
        open={confirmingDelete}
        onOpenChange={(next) => {
          if (!next && !actionBusy) setConfirmingDelete(false);
        }}
        title="Delete process instance?"
        description={`Process instance ${instanceIdParam} and its run data will be permanently deleted. This cannot be undone.`}
        confirmLabel={actionBusy ? 'Deleting…' : 'Delete'}
        pending={actionBusy}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}

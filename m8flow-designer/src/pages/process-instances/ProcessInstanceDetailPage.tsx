import { lazy, Suspense, type ReactNode, useEffect, useState } from 'react';
import { Link2, Pause, Play, Square } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { ApiError } from '@/lib/api';
import {
  fetchProcessInstanceDetail,
  postProcessInstanceLifecycle,
  type ProcessInstanceDetail,
  type ProcessInstanceLifecycleAction,
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

const InstanceDiagramViewer = lazy(() =>
  import('./components/InstanceDiagramViewer').then((m) => ({ default: m.InstanceDiagramViewer })),
);

type DetailTab = 'diagram' | 'milestones' | 'events' | 'messages' | 'tasks';

const TABS: { id: DetailTab; label: string }[] = [
  { id: 'diagram', label: 'Diagram' },
  { id: 'milestones', label: 'Milestones' },
  { id: 'events', label: 'Events' },
  { id: 'messages', label: 'Messages' },
  { id: 'tasks', label: 'Tasks' },
];

function formatUtcTimestamp(epochSeconds: number | null | undefined): string {
  if (epochSeconds == null) {
    return '—';
  }
  const d = new Date(epochSeconds * 1000);
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
 * actions, metadata grid, Tasks I can complete, tab bodies. Download is
 * gone. Copy link is the current URL. Updated / Last milestone come from
 * the designer GET; Revision stays `—` (no git, no hash, no GET key).
 */
export default function ProcessInstanceDetailPage() {
  const { instanceId: instanceIdParam } = useParams<{ instanceId: string }>();
  const { scopedTenantId, needsTenant } = useActiveTenant();
  const { canManageProcesses } = useCapabilities();
  const canLifecycle = Boolean(canManageProcesses);

  const parsedId = Number.isFinite(Number(instanceIdParam)) ? Number(instanceIdParam) : NaN;
  const validId = Number.isFinite(parsedId);

  const [detail, setDetail] = useState<ProcessInstanceDetail | null>(null);
  const [loading, setLoading] = useState(!needsTenant && validId);
  const [notFound, setNotFound] = useState(!validId);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [confirmingTerminate, setConfirmingTerminate] = useState(false);
  const [tab, setTab] = useState<DetailTab>('diagram');

  useEffect(() => {
    if (needsTenant || !validId) {
      setDetail(null);
      setLoading(false);
      setNotFound(!needsTenant && !validId);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);

    fetchProcessInstanceDetail(parsedId, scopedTenantId)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDetail(null);
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load process instance');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [parsedId, validId, scopedTenantId, needsTenant]);

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
      const next = await fetchProcessInstanceDetail(parsedId, scopedTenantId);
      setDetail(next);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update process instance');
    } finally {
      setActionBusy(false);
    }
  }

  const actions = detail && canLifecycle ? processInstanceLifecycleVisibility(detail.status) : null;

  return (
    <div className="flex min-h-screen flex-1 flex-col px-11 py-7">
      <Breadcrumbs
        className="mb-[18px] min-w-0 text-[13.5px] text-muted-foreground"
        LinkComponent={RouterBreadcrumbLink}
        linkClassName="shrink-0 text-info font-semibold"
        lastClassName="min-w-0 truncate font-mono"
        items={[
          { label: 'Process Instances', href: '/process-instances' },
          { label: `${detail?.process_model_display_name ?? instanceIdParam} #${instanceIdParam}` },
        ]}
      />

      <div className="mb-5 flex flex-wrap items-center gap-4">
        <h1 className="m-0 font-display text-[clamp(24px,2.4vw,32px)] font-semibold tracking-tight text-foreground">
          Process Instance ID: {instanceIdParam}
        </h1>
        <div className="flex items-center gap-2">
          <IconAction label="Copy link" onClick={handleCopyLink}>
            <Link2 className="size-4 text-muted-foreground" strokeWidth={1.8} />
          </IconAction>
          {actions?.terminate ? (
            <IconAction
              label="Terminate"
              onClick={() => setConfirmingTerminate(true)}
              disabled={actionBusy}
            >
              <Square className="size-3.5 fill-destructive text-destructive" strokeWidth={0} />
            </IconAction>
          ) : null}
          {actions?.suspend ? (
            <IconAction
              label="Suspend"
              onClick={() => handleLifecycle('suspend')}
              disabled={actionBusy}
            >
              <Pause className="size-3.5 fill-muted-foreground text-muted-foreground" strokeWidth={0} />
            </IconAction>
          ) : null}
          {actions?.resume ? (
            <IconAction
              label="Resume"
              onClick={() => handleLifecycle('resume')}
              disabled={actionBusy}
            >
              <Play className="size-3.5 fill-muted-foreground text-muted-foreground" strokeWidth={0} />
            </IconAction>
          ) : null}
        </div>
      </div>

      {needsTenant ? (
        <p className="text-sm text-muted-foreground">
          Process instances are tenant-scoped. Select a concrete tenant in the sidebar.
        </p>
      ) : loading ? (
        <p className="text-sm text-muted-foreground" aria-busy="true">
          Loading process instance…
        </p>
      ) : notFound ? (
        <p className="text-sm text-muted-foreground" role="status">
          Process instance not found.
        </p>
      ) : error && !detail ? (
        <Alert tone="error">{error}</Alert>
      ) : detail ? (
        <>
          {error ? (
            <Alert tone="error" className="mb-4">
              {error}
            </Alert>
          ) : null}

          <Card variant="bordered" className="mb-[26px] grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-x-7 gap-y-3.5 px-[22px] py-[18px]">
            <MetaCell label="Status">
              <Pill {...processInstanceStatusToPillProps(detail.status)} />
            </MetaCell>
            <MetaCell label="Started by">{detail.started_by || '—'}</MetaCell>
            <MetaCell label="Started">
              <span className="font-mono text-[12.5px]">{formatUtcTimestamp(detail.start_in_seconds)}</span>
            </MetaCell>
            <MetaCell label="Updated">
              <span className="font-mono text-[12.5px]">{formatUtcTimestamp(detail.updated_at_in_seconds)}</span>
            </MetaCell>
            <MetaCell label="Last milestone">
              {detail.last_milestone_bpmn_name?.trim() || '—'}
            </MetaCell>
            <MetaCell label="Revision">
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
                  {item.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {tab === 'diagram' ? (
            detail.bpmn_xml ? (
              <Card variant="bordered" className="relative h-[520px] overflow-hidden">
                <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading diagram…</p>}>
                  <InstanceDiagramViewer xml={detail.bpmn_xml} tasks={detail.tasks} />
                </Suspense>
              </Card>
            ) : (
              <EmptyState
                role="status"
                title="No BPMN diagram is available for this instance (its process definition may have been removed)."
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
            <EmptyState title="No messages recorded for this process instance." />
          ) : null}

          {tab === 'tasks' ? (
            <ProcessInstanceCompletedTasksTable instanceId={parsedId} tenantId={scopedTenantId} />
          ) : null}
        </>
      ) : null}

      <ConfirmDialog
        open={confirmingTerminate}
        onOpenChange={setConfirmingTerminate}
        title="Terminate process instance?"
        description="This cannot be undone."
        confirmLabel="Terminate"
        onConfirm={() => {
          setConfirmingTerminate(false);
          void handleLifecycle('terminate');
        }}
      />
    </div>
  );
}

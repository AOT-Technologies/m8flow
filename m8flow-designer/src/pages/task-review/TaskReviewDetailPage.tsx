import { useEffect, useState, type ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '@/lib/api';
import { SchemaForm, validateSchemaForm, type JsonSchema } from '@/components/SchemaForm';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { Pill, type PillProps } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Timeline, TimelineItem, type TimelineStatus } from '@/components/ui/timeline';
import { cn } from '@/lib/utils';
import { formatRelativeTime } from '@/lib/relativeTime';
import {
  fetchTaskReviewDetail,
  submitTaskReview,
  type SubmitTaskReviewPayload,
  type TaskReviewActivityEvent,
  type TaskReviewApprovalNode,
  type TaskReviewDetail,
} from '@/lib/tasksApi';

// Presentation lives in the frontend (contract §Conventions): the backend
// returns raw status/event enums and this page owns the wording.

/** Task status enum → reviewer-facing label + badge tone. Unknowns humanize. */
const STATUS_LABELS: Record<string, string> = {
  READY: 'Awaiting your review',
  CLAIMED: 'In review',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
};

// `error`/`muted` (not `destructive`/`secondary`) — Pill's own tone
// vocabulary (component-adoption map, ticket 10). `error` is Pill's always-
// tinted look, a deliberate softening from `ui/badge.tsx`'s solid
// `destructive` variant, the same accepted trade-off ticket 15's
// StatusBadge→Pill consolidation made for the analogous process-instance
// status vocabulary.
const STATUS_TONES: Record<string, NonNullable<PillProps['tone']>> = {
  READY: 'info',
  CLAIMED: 'warning',
  COMPLETED: 'success',
  CANCELLED: 'error',
};

/** Raw ProcessInstanceEventModel `event_type` → sentence fragment. */
const EVENT_LABELS: Record<string, string> = {
  process_instance_created: 'started the process',
  process_instance_completed: 'completed the process',
  process_instance_suspended: 'suspended the process',
  process_instance_terminated: 'terminated the process',
  task_completed: 'completed a task',
  task_failed: 'failed a task',
  task_cancelled: 'cancelled a task',
  task_data_edited: 'edited task data',
  human_task_ready: 'became ready for review',
  human_task_completed: 'completed a review',
};

/** Seed form state from the task's values, applying each property `default`
 * only where the key isn't already present in the provided values. */
function initialFormValues(schema: JsonSchema, values: Record<string, unknown>): Record<string, unknown> {
  const next: Record<string, unknown> = { ...values };
  const props = schema.properties ?? {};
  for (const key of Object.keys(props)) {
    if (!(key in next) && props[key].default !== undefined) {
      next[key] = props[key].default;
    }
  }
  return next;
}

function humanize(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/^\w/, (c) => c.toUpperCase());
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? humanize(status);
}

function eventLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType.replace(/_/g, ' ');
}

/** Adapter passed to `Breadcrumbs`' `LinkComponent` for client-side
 * navigation (component-adoption map, ticket 10). */
function RouterBreadcrumbLink({ href, className, children }: BreadcrumbLinkProps) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

function CardShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card variant="bordered">
      <div className="border-b border-border px-6 py-4">
        <h2 className="font-display text-lg">{title}</h2>
      </div>
      <div className="p-6">{children}</div>
    </Card>
  );
}

function ApprovalChainCard({ nodes }: { nodes: TaskReviewApprovalNode[] }) {
  return (
    <CardShell title="Approval chain">
      {nodes.length === 0 ? (
        <p className="text-sm text-muted-foreground">No approval steps recorded.</p>
      ) : (
        <Timeline>
          {nodes.map((node, i) => {
            const status: TimelineStatus = node.completed
              ? 'completed'
              : node.is_current
                ? 'current'
                : 'pending';
            const detail =
              node.completed && node.completed_at_in_seconds != null
                ? `Completed ${formatRelativeTime(node.completed_at_in_seconds)}`
                : node.is_current
                  ? 'Awaiting decision'
                  : statusLabel(node.status);
            return (
              <TimelineItem
                key={i}
                status={status}
                isLast={i === nodes.length - 1}
                className={cn(node.is_current && 'rounded-lg bg-nav-active/10 px-2')}
              >
                <p className="font-medium text-foreground">{node.name ?? 'System'}</p>
                <p className="text-xs text-muted-foreground">
                  {node.lane_name ? `${node.lane_name} · ` : ''}
                  {detail}
                </p>
              </TimelineItem>
            );
          })}
        </Timeline>
      )}
    </CardShell>
  );
}

function ActivityCard({ events }: { events: TaskReviewActivityEvent[] }) {
  return (
    <CardShell title="Activity">
      {events.length === 0 ? (
        <p className="text-sm text-muted-foreground">No activity recorded yet.</p>
      ) : (
        <Timeline>
          {events.map((event, i) => {
            const failed = /fail|error|cancel|terminate/i.test(event.event_type);
            return (
              <TimelineItem key={i} status={failed ? 'pending' : 'completed'} isLast={i === events.length - 1}>
                <p className="text-sm">
                  <span className="font-medium text-foreground">{event.actor_name ?? 'System'}</span>{' '}
                  <span className="text-muted-foreground">{eventLabel(event.event_type)}</span>
                  {event.task_title ? (
                    <span className="text-foreground"> · {event.task_title}</span>
                  ) : null}
                </p>
                <p className="text-xs text-muted-foreground">{formatRelativeTime(event.timestamp)}</p>
              </TimelineItem>
            );
          })}
        </Timeline>
      )}
    </CardShell>
  );
}

function InstanceCard({ instance }: { instance: TaskReviewDetail['instance'] }) {
  const rows: Array<[string, ReactNode]> = [
    ['Instance ID', `#${instance.id}`],
    ['Started', formatRelativeTime(instance.start_in_seconds)],
    [
      'Status',
      instance.status ? (
        <Pill tone="info" dot={false}>{humanize(instance.status)}</Pill>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    ],
    ['Current milestone', instance.last_milestone_bpmn_name ?? '—'],
  ];
  return (
    <CardShell title="Process instance">
      <dl className="space-y-3">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-3">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="text-right text-sm text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      <Link
        to={instance.detail_path}
        className="mt-4 inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
      >
        View full instance <ExternalLink className="size-3.5" />
      </Link>
    </CardShell>
  );
}

/**
 * Task Review — single-task review detail (contract §2/§3). Variant A: a main
 * column (an editable Task Form rendered from the task's JSON schema + outcome
 * actions, then Activity) and a 320px sidebar (approval chain + process-instance
 * summary). Data comes from
 * `fetchTaskReviewDetail` (cookie-scoped, no tenantId); submitting an outcome
 * posts via `submitTaskReview` and returns the reviewer to the inbox. Keyed by
 * the backend `human_task` id from the `:taskId` route param.
 */
export default function TaskReviewDetailPage() {
  const { taskId: taskIdParam } = useParams<{ taskId: string }>();
  const navigate = useNavigate();

  const parsedId = taskIdParam ? Number(taskIdParam) : NaN;
  const validId = Number.isFinite(parsedId);

  const [detail, setDetail] = useState<TaskReviewDetail | null>(null);
  const [loading, setLoading] = useState(validId);
  const [notFound, setNotFound] = useState(!validId);
  const [error, setError] = useState<string | null>(null);

  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

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

    fetchTaskReviewDetail(parsedId)
      .then((payload) => {
        if (cancelled) return;
        setDetail(payload);
        setFormValues(
          initialFormValues(payload.form.schema as JsonSchema, payload.form.values),
        );
        setErrors({});
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDetail(null);
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load task');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [parsedId, validId]);

  function handleSubmit(outcome?: string) {
    if (!validId || submitting || !detail) return;
    if (detail.instance.status === 'suspended') return;

    const validationErrors = validateSchemaForm(detail.form.schema as JsonSchema, formValues);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }
    setErrors({});

    const payload: SubmitTaskReviewPayload = {
      ...formValues,
      ...(outcome !== undefined ? { outcome } : {}),
    };

    setSubmitting(true);
    setSubmitError(null);
    submitTaskReview(parsedId, payload)
      .then(() => {
        navigate('/task-review');
      })
      .catch((err: unknown) => {
        const message =
          err instanceof ApiError && err.serverMessage
            ? err.serverMessage
            : err instanceof Error
              ? err.message
              : 'Failed to submit review';
        setSubmitError(message);
        setSubmitting(false);
      });
  }

  if (notFound) {
    return (
      <main className="flex-1 px-11 py-10">
        <p className="text-sm text-muted-foreground" role="status">
          Task not found.
        </p>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="flex-1 px-11 py-10">
        <p className="text-sm text-muted-foreground" aria-busy="true">
          Loading task…
        </p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="flex-1 px-11 py-10">
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      </main>
    );
  }

  if (!detail) return null;

  const { task, form, outcomes, approval_chain, activity, instance } = detail;
  const instanceSuspended = instance.status === 'suspended';
  const formLocked = submitting || instanceSuspended;

  return (
    <main className="flex-1 px-11 py-10">
      <header className="mb-7 space-y-3">
        <Breadcrumbs
          className="text-[13px] text-muted-foreground"
          LinkComponent={RouterBreadcrumbLink}
          linkClassName="text-info font-normal"
          items={[
            { label: 'Task Review', href: '/task-review' },
            { label: task.task_title || task.task_name },
          ]}
        />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="font-display text-[28px] leading-tight font-semibold tracking-tight">
            {task.task_title || task.task_name}
          </h1>
          <span className="text-sm text-muted-foreground">{task.process_model_display_name}</span>
          <Pill tone={STATUS_TONES[task.status] ?? 'muted'} dot={false} className="ml-auto">
            {statusLabel(task.status)}
          </Pill>
        </div>
        <p className="text-sm text-muted-foreground">
          Submitted by{' '}
          <span className="font-medium text-foreground">{task.submitted_by ?? 'Unknown'}</span>
          {task.created_at_in_seconds != null ? ` · ${formatRelativeTime(task.created_at_in_seconds)}` : ''}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          <Card variant="bordered">
            <div className="border-b border-border px-6 py-4">
              <h2 className="font-display text-lg">Task Form</h2>
            </div>
            <div className="space-y-6 p-6">
              <SchemaForm
                schema={form.schema as JsonSchema}
                uiSchema={form.ui_schema}
                value={formValues}
                onChange={setFormValues}
                errors={errors}
                disabled={formLocked}
              />

              <div className="space-y-4 border-t border-border pt-5">
                {instanceSuspended ? (
                  <p className="text-sm text-muted-foreground" role="status">
                    This process instance is suspended. Resume it before submitting.
                  </p>
                ) : null}
                {submitError ? (
                  <p className="text-sm text-destructive" role="alert">
                    {submitError}
                  </p>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  {outcomes.length > 0 ? (
                    outcomes.map((outcome, i) => (
                      <Button
                        key={outcome.value}
                        type="button"
                        variant={i === 0 ? 'pill' : 'pill-outline'}
                        size="pill"
                        disabled={formLocked}
                        onClick={() => handleSubmit(outcome.value)}
                      >
                        {outcome.label}
                      </Button>
                    ))
                  ) : (
                    <Button
                      type="button"
                      variant="pill"
                      size="pill"
                      disabled={formLocked}
                      onClick={() => handleSubmit()}
                    >
                      Submit
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </Card>

          <ActivityCard events={activity} />
        </div>

        <aside className="space-y-6">
          <ApprovalChainCard nodes={approval_chain} />
          <InstanceCard instance={instance} />
        </aside>
      </div>
    </main>
  );
}

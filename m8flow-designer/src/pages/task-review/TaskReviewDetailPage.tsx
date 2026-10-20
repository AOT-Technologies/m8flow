import { useEffect, useState, type ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import type { ParseKeys } from 'i18next';
import { Trans, useTranslation } from 'react-i18next';

import i18n, { literalTransValues } from '@/i18n';
import { ApiError } from '@/lib/api';
import { useCapabilities } from '@/components/session/hooks';
import { SchemaForm, validateSchemaForm, type JsonSchema } from '@/components/SchemaForm';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { Pill, type PillProps } from '@/components/library/pill/Pill';
import { processInstanceStatusLabel } from '@/components/library/pill/processInstanceStatusToPillProps';
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
const STATUS_LABELS: Record<string, ParseKeys> = {
  READY: 'taskReview.detail.status.ready',
  CLAIMED: 'taskReview.detail.status.claimed',
  COMPLETED: 'taskReview.detail.status.completed',
  CANCELLED: 'taskReview.detail.status.cancelled',
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
const EVENT_LABELS: Record<string, ParseKeys> = {
  process_instance_created: 'taskReview.detail.events.processInstanceCreated',
  process_instance_completed: 'taskReview.detail.events.processInstanceCompleted',
  process_instance_suspended: 'taskReview.detail.events.processInstanceSuspended',
  process_instance_terminated: 'taskReview.detail.events.processInstanceTerminated',
  task_completed: 'taskReview.detail.events.taskCompleted',
  task_failed: 'taskReview.detail.events.taskFailed',
  task_cancelled: 'taskReview.detail.events.taskCancelled',
  task_data_edited: 'taskReview.detail.events.taskDataEdited',
  human_task_ready: 'taskReview.detail.events.humanTaskReady',
  human_task_completed: 'taskReview.detail.events.humanTaskCompleted',
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
  const key = STATUS_LABELS[status];
  return key ? i18n.t(key) : humanize(status);
}

function eventLabel(eventType: string): string {
  const key = EVENT_LABELS[eventType];
  return key ? i18n.t(key) : eventType.replace(/_/g, ' ');
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
  const { t } = useTranslation();
  return (
    <CardShell title={t('taskReview.detail.approvalChain.title')}>
      {nodes.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('taskReview.detail.approvalChain.empty')}</p>
      ) : (
        <Timeline>
          {nodes.map((node, i) => {
            const status: TimelineStatus = node.completed
              ? 'completed'
              : node.is_current
                ? 'current'
                : 'pending';
            const detail =
              node.completed && node.completed_at != null
                ? t('taskReview.detail.approvalChain.completedAgo', { time: formatRelativeTime(node.completed_at) })
                : node.is_current
                  ? t('taskReview.detail.approvalChain.awaitingDecision')
                  : statusLabel(node.status);
            return (
              <TimelineItem
                key={i}
                status={status}
                isLast={i === nodes.length - 1}
                className={cn(node.is_current && 'rounded-lg bg-nav-active/10 px-2')}
              >
                <p className="font-medium text-foreground">{node.name ?? t('taskReview.system')}</p>
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
  const { t } = useTranslation();
  return (
    <CardShell title={t('taskReview.detail.activity.title')}>
      {events.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('taskReview.detail.activity.empty')}</p>
      ) : (
        <Timeline>
          {events.map((event, i) => {
            const failed = /fail|error|cancel|terminate/i.test(event.event_type);
            return (
              <TimelineItem key={i} status={failed ? 'pending' : 'completed'} isLast={i === events.length - 1}>
                <p className="text-sm">
                  <span className="font-medium text-foreground">{event.actor_name ?? t('taskReview.system')}</span>{' '}
                  <span className="text-muted-foreground">{eventLabel(event.event_type)}</span>
                  {event.task_title ? (
                    <span className="text-foreground"> · {event.task_title}</span>
                  ) : null}
                </p>
                <p className="text-xs text-muted-foreground">{formatRelativeTime(event.occurred_at)}</p>
              </TimelineItem>
            );
          })}
        </Timeline>
      )}
    </CardShell>
  );
}

function InstanceCard({ instance }: { instance: TaskReviewDetail['instance'] }) {
  const { t } = useTranslation();
  const rows: Array<[string, ReactNode]> = [
    [t('taskReview.detail.instance.instanceId'), `#${instance.id}`],
    [t('taskReview.detail.instance.started'), formatRelativeTime(instance.started_at)],
    [
      t('common.status'),
      instance.status ? (
        <Pill tone="info" dot={false}>{processInstanceStatusLabel(instance.status)}</Pill>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    ],
    [t('taskReview.detail.instance.currentMilestone'), instance.last_milestone_bpmn_name ?? '—'],
  ];
  return (
    <CardShell title={t('taskReview.detail.instance.title')}>
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
        {t('taskReview.detail.instance.viewFull')} <ExternalLink className="size-3.5" />
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
  const { t } = useTranslation();
  const { canSubmitTaskReviews } = useCapabilities();
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
          setError(err instanceof Error ? err.message : i18n.t('taskReview.detail.loadError'));
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
    if (!canSubmitTaskReviews || !validId || submitting || !detail || detail.task.completed) return;
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
              : t('taskReview.detail.submitError');
        setSubmitError(message);
        setSubmitting(false);
      });
  }

  if (notFound) {
    return (
      <main className="flex-1 px-11 py-10">
        <p className="text-sm text-muted-foreground" role="status">
          {t('taskReview.detail.notFound')}
        </p>
      </main>
    );
  }

  if (loading) {
    return (
      <main className="flex-1 px-11 py-10">
        <p className="text-sm text-muted-foreground" aria-busy="true">
          {t('taskReview.detail.loading')}
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
  const formLocked = !canSubmitTaskReviews || submitting || instanceSuspended || task.completed;

  return (
    <main className="flex-1 px-11 py-10">
      <header className="mb-7 space-y-3">
        <Breadcrumbs
          className="text-[13px] text-muted-foreground"
          LinkComponent={RouterBreadcrumbLink}
          linkClassName="text-info font-normal"
          items={[
            { label: t('taskReview.title'), href: '/task-review' },
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
          <Trans
            {...literalTransValues}
            i18nKey="taskReview.detail.submittedBy"
            values={{ name: task.submitted_by ?? t('taskReview.detail.unknownSubmitter') }}
            components={{ name: <span className="font-medium text-foreground" /> }}
          />
          {task.created_at != null ? ` · ${formatRelativeTime(task.created_at)}` : ''}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          <Card variant="bordered">
            <div className="border-b border-border px-6 py-4">
              <h2 className="font-display text-lg">{t('taskReview.detail.taskForm')}</h2>
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
                    {t('taskReview.detail.instanceSuspended')}
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
                      {t('taskReview.detail.submit')}
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

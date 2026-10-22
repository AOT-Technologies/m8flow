import { useState } from 'react';
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

import i18n, { formatLocale } from '@/i18n';
import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Modal } from '@/components/library/modal/Modal';
import { Pill, type PillProps } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ApiError } from '@/lib/api';
import type { CeleryControlResult, CeleryTaskState } from '@/lib/celeryApi';
import { formatDuration } from '@/pages/nats/natsShared';

export type Tone = NonNullable<PillProps['tone']>;
export type Notice = { tone: 'success' | 'error'; text: string };

/** A disabled monitor or a stopped broker is an expected state; the backend message says which. */
export function celeryErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.serverMessage) return err.serverMessage;
    if (err.status === 503) return i18n.t('celery.errors.unreachable');
    return err.message;
  }
  return i18n.t('celery.errors.loadFailed');
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—';
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? '—' : new Date(ms).toLocaleString(formatLocale());
}

/** 0.0042 -> "4 ms", 1.5 -> "1.50 s", 125 -> "2m 5s". */
export function formatRuntime(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  if (seconds < 1) return `${Math.round(seconds * 1000).toLocaleString(formatLocale())} ms`;
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  return formatDuration(seconds);
}

export const STATE_TONE: Record<CeleryTaskState, Tone> = {
  RECEIVED: 'info',
  STARTED: 'info',
  SUCCESS: 'success',
  FAILURE: 'error',
  RETRY: 'warning',
  REVOKED: 'muted',
};

export const STATE_LABEL: Record<CeleryTaskState, ParseKeys> = {
  RECEIVED: 'celery.states.RECEIVED',
  STARTED: 'celery.states.STARTED',
  SUCCESS: 'celery.states.SUCCESS',
  FAILURE: 'celery.states.FAILURE',
  RETRY: 'celery.states.RETRY',
  REVOKED: 'celery.states.REVOKED',
};

/** Tasks a revoke or terminate can still affect. */
export const UNFINISHED_STATES: readonly CeleryTaskState[] = ['RECEIVED', 'STARTED', 'RETRY'];

export function StateBadge({ state }: { state: CeleryTaskState }) {
  const { t } = useTranslation();
  return (
    <Pill size="lg" tone={STATE_TONE[state] ?? 'muted'}>
      {STATE_LABEL[state] ? t(STATE_LABEL[state]) : state}
    </Pill>
  );
}

/** What the workers answered, as one line for the page notice. */
export function controlNotice(result: CeleryControlResult): Notice {
  if (result.ok) return { tone: 'success', text: result.message || i18n.t('celery.control.done') };
  const failures = result.results.filter((reply) => !reply.ok).map((reply) => `${reply.worker}: ${reply.message}`);
  return { tone: 'error', text: result.message || failures.join('; ') || i18n.t('celery.control.failed') };
}

export type ActionField = {
  key: string;
  label: string;
  type?: 'text' | 'number';
  placeholder?: string;
  defaultValue?: string;
};

/**
 * One control action. Without fields it is a confirmation; with fields it is a small
 * form whose validation errors stay in the dialog. The backend's answer goes to `onDone`.
 */
export function CeleryActionDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = false,
  fields = [],
  onSubmit,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  fields?: ActionField[];
  onSubmit: (values: Record<string, string>) => Promise<CeleryControlResult>;
  onDone: (notice: Notice) => void;
}) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset(next: boolean) {
    if (!next) {
      setValues({});
      setError(null);
    }
    onOpenChange(next);
  }

  async function submit() {
    setPending(true);
    setError(null);
    try {
      const filled = Object.fromEntries(fields.map((field) => [field.key, values[field.key] ?? field.defaultValue ?? '']));
      const result = await onSubmit(filled);
      onDone(controlNotice(result));
      reset(false);
    } catch (err) {
      const message = celeryErrorMessage(err);
      // A bad value is fixed in the form; anything else is reported on the page.
      if (fields.length && err instanceof ApiError && err.status === 400) {
        setError(message);
      } else {
        onDone({ tone: 'error', text: message });
        reset(false);
      }
    } finally {
      setPending(false);
    }
  }

  if (!fields.length) {
    return (
      <ConfirmDialog
        open={open}
        onOpenChange={reset}
        title={title}
        description={description}
        confirmLabel={confirmLabel}
        cancelLabel={t('common.cancel')}
        tone={destructive ? 'destructive' : 'default'}
        pending={pending}
        onConfirm={() => void submit()}
      />
    );
  }

  return (
    <Modal
      open={open}
      onOpenChange={reset}
      title={title}
      footer={
        <>
          <Button variant="pill-outline" onClick={() => reset(false)} disabled={pending}>
            {t('common.cancel')}
          </Button>
          <Button variant={destructive ? 'destructive' : 'pill-dark'} onClick={() => void submit()} disabled={pending}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">{description}</p>
        {fields.map((field) => (
          <label key={field.key} className="flex flex-col gap-1.5 text-[13px] font-medium text-foreground">
            {field.label}
            <Input
              type={field.type ?? 'text'}
              value={values[field.key] ?? field.defaultValue ?? ''}
              placeholder={field.placeholder}
              onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
            />
          </label>
        ))}
        {error && <Alert tone="error">{error}</Alert>}
      </div>
    </Modal>
  );
}

/** Dialog state for one action at a time: which action, and on what. */
export function useActionDialog<T>() {
  const [target, setTarget] = useState<T | null>(null);
  return {
    target,
    open: (next: T) => setTarget(next),
    props: {
      open: target !== null,
      onOpenChange: (next: boolean) => {
        if (!next) setTarget(null);
      },
    },
  };
}

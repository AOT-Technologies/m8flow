import type { ReactNode } from 'react';
import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * Minimal vertical step-indicator. A single primitive drives both the Task
 * Review approval chain (rich nodes) and the activity log (simple events):
 *
 * - `completed` — filled check (success)
 * - `current`   — highlighted with `--nav-active`
 * - `pending`   — muted outline dot
 *
 * Layout is intentionally content-agnostic: `<Timeline>` is the `<ol>`,
 * `<TimelineItem>` renders the indicator + connector rail and yields its
 * `children` as the row body, so callers own all node/event markup.
 */
export type TimelineStatus = 'completed' | 'current' | 'pending';

export function Timeline({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <ol className={cn('relative', className)}>{children}</ol>;
}

function TimelineIndicator({ status }: { status: TimelineStatus }) {
  return (
    <span
      className={cn(
        'z-10 mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border bg-card',
        status === 'completed' && 'border-success bg-success/10 text-success',
        status === 'current' && 'border-nav-active bg-nav-active/20 text-nav-active',
        status === 'pending' && 'border-border text-muted-foreground',
      )}
      aria-hidden
    >
      {status === 'completed' ? (
        <Check className="size-3" strokeWidth={2.5} />
      ) : (
        <span
          className={cn(
            'rounded-full bg-current',
            status === 'current' ? 'size-2' : 'size-1.5',
          )}
        />
      )}
    </span>
  );
}

export function TimelineItem({
  status = 'pending',
  isLast = false,
  children,
  className,
}: {
  status?: TimelineStatus;
  /** Suppresses the connector rail below the final item. */
  isLast?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <li className={cn('relative flex gap-3 pb-4 last:pb-0', className)}>
      {isLast ? null : (
        <span
          className="absolute top-6 bottom-0 left-[9px] w-px bg-border"
          aria-hidden
        />
      )}
      <TimelineIndicator status={status} />
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  );
}

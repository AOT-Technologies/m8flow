import type { ComponentType, ReactNode, SVGProps } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StatCardProps {
  /** Any lucide-react icon component (or compatible SVG component). */
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Tailwind classes for the icon badge's background + icon color, e.g. "bg-info/10 text-info". */
  iconClassName?: string;
  value: ReactNode;
  label: string;
  /** Destination list (with filters). Omit to render a plain, non-clickable card. */
  to?: string;
  /** What the card counts; shown as the native hover tooltip. */
  description?: string;
}

/**
 * One of Home's stat cards — icon badge with label on one row, big number below.
 * With `to`, the whole card is a link to the matching filtered list.
 */
export function StatCard({ icon: Icon, iconClassName, value, label, to, description }: StatCardProps) {
  const card = (
    <Card
      className={cn(
        'h-full transition-shadow',
        to && 'group-hover/stat:shadow-md group-hover/stat:ring-foreground/20',
      )}
    >
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'flex size-9 items-center justify-center rounded-full',
              iconClassName,
            )}
          >
            <Icon className="size-4" />
          </span>
          <span className="text-sm text-muted-foreground">{label}</span>
        </div>
        <span className="text-3xl font-semibold tracking-tight text-foreground">{value}</span>
      </CardContent>
    </Card>
  );

  if (!to) {
    return <div title={description}>{card}</div>;
  }
  return (
    <Link
      to={to}
      title={description}
      className="group/stat block rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {card}
    </Link>
  );
}

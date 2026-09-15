import type { ComponentType, ReactNode, SVGProps } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StatCardProps {
  /** Any lucide-react icon component (or compatible SVG component). */
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Tailwind classes for the icon badge's background + icon color, e.g. "bg-info/10 text-info". */
  iconClassName?: string;
  value: ReactNode;
  label: string;
}

/**
 * One of Home's 6 stat cards — icon badge with label on one row, big number below.
 * Generalizes the pattern m8flow-frontend's page-scoped `ActivityMetricCard`
 * (McpConnection.tsx) established, as a shared, mockup-styled component.
 */
export function StatCard({ icon: Icon, iconClassName, value, label }: StatCardProps) {
  return (
    <Card>
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
}

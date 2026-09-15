import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { AlertCircle, AlertTriangle, CheckCircle, Info } from "lucide-react"

import { cn } from "@/lib/utils"

const alertVariants = cva(
  "flex items-start gap-2.5 rounded-[10px] border px-4 py-3",
  {
    variants: {
      // Same tone->token pale-surface mapping as `library/pill/Pill.tsx`
      // (ticket 06): `bg-{tone}/10 text-{tone}`. "info" is the one tone
      // Pill doesn't have — `--info` already exists as a token.
      tone: {
        success: "bg-success/10 border-success/20",
        warning: "bg-warning/10 border-warning/20",
        error: "bg-destructive/10 border-destructive/20",
        info: "bg-info/10 border-info/20",
      },
    },
    defaultVariants: {
      tone: "info",
    },
  }
)

const alertIconClassName: Record<
  NonNullable<VariantProps<typeof alertVariants>["tone"]>,
  string
> = {
  success: "text-success",
  warning: "text-warning",
  error: "text-destructive",
  info: "text-info",
}

const alertIconByTone: Record<
  NonNullable<VariantProps<typeof alertVariants>["tone"]>,
  React.ComponentType<React.SVGProps<SVGSVGElement>>
> = {
  success: CheckCircle,
  warning: AlertTriangle,
  error: AlertCircle,
  info: Info,
}

export interface AlertProps
  extends React.ComponentPropsWithoutRef<"div">,
    VariantProps<typeof alertVariants> {
  /** Message text/content. A prop, not hardcoded copy. */
  children: React.ReactNode
}

function Alert({ className, tone = "info", children, ...props }: AlertProps) {
  const resolvedTone = tone ?? "info"
  const Icon = alertIconByTone[resolvedTone]

  return (
    <div
      role="alert"
      data-slot="alert"
      data-tone={resolvedTone}
      className={cn(alertVariants({ tone: resolvedTone }), className)}
      {...props}
    >
      <Icon
        aria-hidden="true"
        data-slot="alert-icon"
        className={cn("size-[17px] shrink-0", alertIconClassName[resolvedTone])}
      />
      <span
        data-slot="alert-message"
        className="text-[13.5px] leading-[1.4] text-foreground"
      >
        {children}
      </span>
    </div>
  )
}

export { Alert, alertVariants }

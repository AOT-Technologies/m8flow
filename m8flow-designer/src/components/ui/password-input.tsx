import * as React from "react"
import { Eye, EyeOff } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

// Masked input with an eye toggle. Visibility is local state, so the value is
// masked on mount and re-masks whenever the field unmounts. `className` styles
// the wrapper (margins) so the absolutely-positioned toggle stays aligned.
function PasswordInput({
  className,
  toggleLabel,
  ...props
}: Omit<React.ComponentProps<"input">, "type"> & { toggleLabel: string }) {
  const { t } = useTranslation()
  const [shown, setShown] = React.useState(false)
  return (
    <div className={cn("relative", className)}>
      <Input {...props} className="pr-9" type={shown ? "text" : "password"} />
      <button
        type="button"
        className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-lg text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        aria-label={t(shown ? "common.hideValue" : "common.showValue", { label: toggleLabel })}
        aria-pressed={shown}
        onClick={() => setShown((prev) => !prev)}
      >
        {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
      </button>
    </div>
  )
}

export { PasswordInput }

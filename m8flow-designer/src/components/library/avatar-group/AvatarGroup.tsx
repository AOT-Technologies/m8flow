import * as React from "react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"

export interface AvatarGroupItem {
  /** Initials (or other short fallback text) shown inside the avatar. */
  initials: string
  /**
   * Background/text color for this avatar, e.g. `"bg-foreground text-white"`.
   * Left to the caller rather than a fixed palette — the mockup's per-avatar
   * colors (raspberry, sky-blue, gunmetal, success-green, ...) are
   * per-instance choices, same reasoning as `ui/avatar.tsx`'s own
   * `AvatarFallback` default.
   */
  className?: string
}

export interface AvatarGroupProps
  extends Omit<React.ComponentPropsWithoutRef<"div">, "children"> {
  /** Avatars to render, left to right. */
  items: AvatarGroupItem[]
  /**
   * Max number of avatars to show before collapsing the rest into a
   * trailing "+N" overflow avatar. Defaults to showing every item
   * (no overflow) when omitted.
   */
  max?: number
  /**
   * Size applied to every avatar in the group (including the overflow
   * avatar). Defaults to `"sm"` (28px) — the closest entry in
   * `ui/avatar.tsx`'s size scale (sm 28 / md 36 / lg 44) to the mockup's
   * 32px overlapping-stack avatars. Neither scale step lands on 32px
   * exactly; `sm` was picked per this ticket's explicit instruction. See
   * ticket 10's Answer for the full note.
   */
  size?: "sm" | "md" | "lg"
  /**
   * Class override for the trailing "+N" overflow avatar's
   * background/text color. Defaults to the mockup's `bg-success text-white`.
   */
  overflowClassName?: string
}

// New composition logic (not a pass-through, unlike `library/avatar`): the
// overlapping stack pattern — negative margin pulling each avatar left
// under the previous one, a white "cutout" ring (`border-2 border-card`,
// `--card` matching the page background) between them, and an optional
// trailing "+N" overflow avatar once `items.length` exceeds `max`.
const AvatarGroup = React.forwardRef<HTMLDivElement, AvatarGroupProps>(
  ({ items, max, size = "sm", overflowClassName, className, ...props }, ref) => {
    const visibleCount = max === undefined ? items.length : Math.min(max, items.length)
    const visibleItems = items.slice(0, visibleCount)
    const overflowCount = items.length - visibleItems.length

    return (
      <div
        ref={ref}
        data-slot="avatar-group"
        className={cn("flex items-center", className)}
        {...props}
      >
        {visibleItems.map((item, index) => (
          <Avatar
            key={index}
            size={size}
            className={cn("border-2 border-card", index > 0 && "-ml-2")}
          >
            <AvatarFallback className={item.className}>{item.initials}</AvatarFallback>
          </Avatar>
        ))}
        {overflowCount > 0 && (
          <Avatar
            size={size}
            className={cn("border-2 border-card", visibleItems.length > 0 && "-ml-2")}
          >
            <AvatarFallback className={overflowClassName ?? "bg-success text-white"}>
              +{overflowCount}
            </AvatarFallback>
          </Avatar>
        )}
      </div>
    )
  }
)
AvatarGroup.displayName = "AvatarGroup"

export { AvatarGroup }

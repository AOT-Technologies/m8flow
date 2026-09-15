import * as React from "react"
import { Avatar as AvatarPrimitive } from "radix-ui"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// forwardRef throughout — same reasoning as dialog.tsx/tooltip.tsx: Radix's
// Image/Fallback swap is Presence-driven internally, so a real ref matters
// here too, not just for content that visibly animates in/out.

const avatarVariants = cva(
  "relative flex shrink-0 overflow-hidden rounded-full",
  {
    variants: {
      // Mockup's "Avatar" section shows three solo sizes (44/36/28px) plus
      // a 32px pair in the overlapping AvatarGroup — that fourth size is
      // AvatarGroup's own concern (ticket 10), not this primitive's.
      size: {
        sm: "size-7", // 28px
        md: "size-9", // 36px
        lg: "size-11", // 44px
      },
    },
    defaultVariants: {
      size: "md",
    },
  }
)

const Avatar = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Root>,
  React.ComponentProps<typeof AvatarPrimitive.Root> & VariantProps<typeof avatarVariants>
>(({ className, size, ...props }, ref) => (
  <AvatarPrimitive.Root
    ref={ref}
    data-slot="avatar"
    className={cn(avatarVariants({ size }), className)}
    {...props}
  />
))
Avatar.displayName = "Avatar"

const AvatarImage = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Image>,
  React.ComponentProps<typeof AvatarPrimitive.Image>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Image
    ref={ref}
    data-slot="avatar-image"
    className={cn("aspect-square size-full object-cover", className)}
    {...props}
  />
))
AvatarImage.displayName = "AvatarImage"

const AvatarFallback = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Fallback>,
  React.ComponentProps<typeof AvatarPrimitive.Fallback>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Fallback
    ref={ref}
    data-slot="avatar-fallback"
    className={cn(
      // Neutral default — the mockup's per-avatar colors (raspberry,
      // sky-blue, gunmetal, success-green, ...) are per-instance choices,
      // not something this primitive should hardcode. Override via
      // `className` (e.g. "bg-primary text-primary-foreground").
      "flex size-full items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground",
      className
    )}
    {...props}
  />
))
AvatarFallback.displayName = "AvatarFallback"

export { Avatar, AvatarImage, AvatarFallback }

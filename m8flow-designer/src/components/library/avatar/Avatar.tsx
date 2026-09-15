// Thin pass-through, not a rewrite. `ui/avatar.tsx` (ticket 02) already
// covers everything the mockup's solo-avatar examples need — three sizes,
// initials-only fallback, image slot for future use. There's no
// library-layer behavior to add on top (no new variants, no new
// composition), so this file exists purely to keep the library's import
// surface consistent (`@/components/library/avatar/Avatar`) rather than
// forcing consumers to reach into `ui/` directly. See ticket 10.
export { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar"

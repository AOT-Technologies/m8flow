import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { cn } from "@/lib/utils"

export interface BreadcrumbItem {
  label: string
  /** Rendered via `LinkComponent` (a plain `<a>` by default) when present. */
  href?: string
}

export interface BreadcrumbLinkProps {
  href: string
  className?: string
  children: React.ReactNode
}

function DefaultBreadcrumbLink({ href, className, children }: BreadcrumbLinkProps) {
  return (
    <a href={href} className={className}>
      {children}
    </a>
  )
}

export interface BreadcrumbsProps
  extends Omit<React.ComponentProps<"nav">, "children"> {
  /** Ordered crumb trail. The last item is always rendered as bold static text, never a link, regardless of whether it has an `href`. */
  items: BreadcrumbItem[]
  /**
   * Overrides how a linked (non-last) crumb renders — e.g. an adapter
   * around `react-router-dom`'s `Link` for client-side navigation:
   * `({ href, className, children }) => <Link to={href} className={className}>{children}</Link>`.
   * Defaults to a plain `<a>`, unchanged for any caller that doesn't pass
   * one. `library/breadcrumbs` still doesn't import `react-router-dom`
   * itself — this keeps it self-contained/router-agnostic (the
   * `m8flow-designer-component-library` map's original design decision)
   * while letting a page opt into SPA navigation instead of a full page
   * reload on every non-last crumb.
   */
  LinkComponent?: React.ComponentType<BreadcrumbLinkProps>
  /**
   * Overrides the linked (non-last) crumb's color/weight classes, merged
   * onto the default (`font-medium text-primary no-underline
   * hover:underline`) via `cn()` — the same merge pattern `className`
   * already uses on the `<nav>`. Defaults to unchanged `text-primary`
   * (the mockup's own pink) for any caller that doesn't pass one.
   * Every real page that's adopted `Breadcrumbs` so far actually wants
   * `text-info` instead (component-adoption map, ticket 24) — pass
   * `linkClassName="text-info"` to reproduce that look rather than
   * baking it in as this component's new default, since a future
   * consumer may still want the mockup's original color.
   */
  linkClassName?: string
  /**
   * Overrides the last (current-page) crumb's classes, merged onto the
   * default (`font-semibold text-foreground [overflow-wrap:anywhere]`) via
   * `cn()` — the same merge pattern `linkClassName` already uses. Defaults
   * to unchanged plain prose styling for any caller that doesn't pass one.
   * Every confirmed consumer whose last crumb is a technical identifier
   * (an instance id, a file name, a group/id path) rather than prose wants
   * `font-mono` instead (component-adoption map, ticket 26) — pass
   * `lastClassName="font-mono"` to reproduce that look. At least one real
   * consumer's last crumb *is* prose (a tenant display name) and matches
   * this default exactly, confirming `font-mono` shouldn't become the new
   * baseline.
   */
  lastClassName?: string
}

/**
 * Breadcrumb trail: every item but the last renders as a link (or plain text
 * if it has no `href`) followed by a chevron separator; the last item
 * renders as bold, non-interactive text and is allowed to wrap
 * (`overflow-wrap: anywhere`) so a long final crumb (e.g. a process model
 * name) doesn't overflow its container.
 */
const Breadcrumbs = React.forwardRef<HTMLElement, BreadcrumbsProps>(
  (
    { items, className, LinkComponent = DefaultBreadcrumbLink, linkClassName, lastClassName, ...props },
    ref
  ) => {
    return (
      <nav
        ref={ref}
        data-slot="breadcrumbs"
        aria-label="Breadcrumb"
        className={cn("text-[13.5px]", className)}
        {...props}
      >
        <ol className="flex flex-wrap items-center gap-1.5">
          {items.map((item, index) => {
            const isLast = index === items.length - 1

            return (
              <li key={`${item.label}-${index}`} className="flex items-center gap-1.5">
                {isLast ? (
                  <span
                    aria-current="page"
                    className={cn(
                      "font-semibold text-foreground [overflow-wrap:anywhere]",
                      lastClassName
                    )}
                  >
                    {item.label}
                  </span>
                ) : (
                  <>
                    {item.href ? (
                      <LinkComponent
                        href={item.href}
                        className={cn(
                          "font-medium text-primary no-underline hover:underline",
                          linkClassName
                        )}
                      >
                        {item.label}
                      </LinkComponent>
                    ) : (
                      <span className="font-medium text-muted-foreground">{item.label}</span>
                    )}
                    <ChevronRight
                      className="size-[13px] shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                  </>
                )}
              </li>
            )
          })}
        </ol>
      </nav>
    )
  }
)
Breadcrumbs.displayName = "Breadcrumbs"

export interface BackLinkProps extends React.ComponentProps<"a"> {
  children: React.ReactNode
  /**
   * Overrides the rendered element for client-side navigation — e.g. an
   * adapter around `react-router-dom`'s `Link`, the same shape as
   * `Breadcrumbs`' own `LinkComponent` prop (component-adoption map, ticket
   * 22 / ticket 07): `({href, className, children}) => <Link to={href}
   * className={className}>{children}</Link>`. Requires `href` to also be
   * set (the adapter needs a target). Defaults to a plain `<a>`, unchanged
   * for any caller that doesn't pass one — `library/breadcrumbs` still
   * doesn't import `react-router-dom` itself.
   */
  LinkComponent?: React.ComponentType<BreadcrumbLinkProps>
}

/**
 * "← Back link variant" from the mockup's Breadcrumbs section — kept in the
 * same folder/family as `Breadcrumbs` since the mockup presents them
 * together, but exported independently so an app that only ever needs one
 * of the two still tree-shakes out the other.
 */
const BackLink = React.forwardRef<HTMLAnchorElement, BackLinkProps>(
  ({ className, children, LinkComponent, href, ...props }, ref) => {
    const mergedClassName = cn(
      "inline-flex items-center gap-1.5 text-[13px] font-semibold text-foreground no-underline hover:underline",
      className
    )
    const content = (
      <>
        <ChevronLeft className="size-3.5 shrink-0" aria-hidden="true" />
        {children}
      </>
    )

    if (LinkComponent && href) {
      return (
        <LinkComponent href={href} className={mergedClassName}>
          {content}
        </LinkComponent>
      )
    }

    return (
      <a ref={ref} data-slot="back-link" href={href} className={mergedClassName} {...props}>
        {content}
      </a>
    )
  }
)
BackLink.displayName = "BackLink"

export { Breadcrumbs, BackLink }

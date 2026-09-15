import { useState } from 'react';
import { Building2, Check, ChevronDown, Loader2 } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { finalizeTenantLogin, getSelectedTenantId, type OrganizationMembership } from '@/lib/auth';

export type TenantSwitcherProps = {
  activeTenantLabel: string;
  organizations: OrganizationMembership[];
};

/**
 * Interactive nav-tenant-name control for a non-super-admin shared-realm user
 * with >=2 org memberships (Sidebar renders the read-only chip below that).
 *
 * The switch reuses the same backend finalization hop the "Select a tenant"
 * gate uses (`finalizeTenantLogin` -> GET /v1.0/login?...&tenant=X&
 * tenant_finalization=1): the backend records the active org, refresh-remints a
 * Keycloak token carrying the target tenant's claims, updates the
 * m8flow_selected_tenant cookie, and redirects back here -- so the page reloads
 * itself with the new tenant, no manual reload and no iframe. (The former
 * prompt=none hidden-iframe mechanism was retired: Keycloak 26 cannot silently
 * re-mint an org-scoped token -- active-tenant deep-module map, ticket 08/10/11.)
 */
export function TenantSwitcher({ activeTenantLabel, organizations }: TenantSwitcherProps) {
  const [switching, setSwitching] = useState(false);

  const selectedTenantId = getSelectedTenantId();
  const isActive = (org: OrganizationMembership) =>
    (org.id != null && org.id === selectedTenantId) || org.alias === selectedTenantId;

  function startSwitch(org: OrganizationMembership) {
    // A full-page navigation to the backend finalization hop, which redirects
    // back here once the cookie + re-minted token are set. Flip a brief
    // "switching" state so the click registers before the page leaves.
    setSwitching(true);
    finalizeTenantLogin(org);
  }

  return (
    <div className="px-6 pb-4">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            data-testid="nav-tenant-name"
            title={activeTenantLabel}
            disabled={switching}
            className="flex w-full items-center gap-2 rounded-lg border border-border bg-sidebar px-2.5 py-2 text-left outline-none select-none focus-visible:ring-2 focus-visible:ring-nav-active/40 disabled:cursor-wait disabled:opacity-70"
          >
            <Building2 className="size-3.5 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">Tenant</div>
              <div className="truncate text-sm font-semibold text-foreground">{activeTenantLabel}</div>
            </div>
            {switching ? (
              <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" aria-hidden />
            ) : (
              <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            )}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[216px]">
          {organizations.map((org) => {
            const active = isActive(org);
            return (
              <DropdownMenuItem
                key={org.alias}
                data-testid={`nav-tenant-option-${org.alias}`}
                disabled={active || switching}
                onSelect={() => {
                  if (!active) {
                    startSwitch(org);
                  }
                }}
              >
                {active ? (
                  <Check className="size-3.5 shrink-0 text-primary" aria-hidden />
                ) : (
                  <span className="size-3.5 shrink-0" aria-hidden />
                )}
                <span className="truncate">{org.name ?? org.alias}</span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

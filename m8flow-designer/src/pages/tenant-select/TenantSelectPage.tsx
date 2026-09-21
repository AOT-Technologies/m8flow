import { Building2, Info } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { fetchOrganizationMemberships } from '@/lib/api';
import {
  clearSelectedTenantCookie,
  finalizeTenantLogin,
  getCurrentUser,
  getOrganizationMemberships,
  isLoggedIn,
  login,
  logout,
  type OrganizationMembership,
} from '@/lib/auth';

function designerRootUrl(): string {
  return `${window.location.origin}/`;
}

// The directory response is the authoritative membership list (the JWT's
// `organization` claim only ever carries the single "active" org, never the
// full list). Backfill names from the token where the directory left one
// blank; never drop directory entries the token didn't know about.
function mergeOrganizationMemberships(
  currentMemberships: OrganizationMembership[],
  resolvedMemberships: OrganizationMembership[],
): OrganizationMembership[] {
  const currentByKey = new Map<string, OrganizationMembership>();
  for (const membership of currentMemberships) {
    if (membership.id) {
      currentByKey.set(`id:${membership.id}`, membership);
    }
    currentByKey.set(`alias:${membership.alias}`, membership);
  }

  return resolvedMemberships.map((membership) => {
    const known =
      (membership.id && currentByKey.get(`id:${membership.id}`)) ||
      currentByKey.get(`alias:${membership.alias}`);
    if (!known) {
      return membership;
    }
    return {
      alias: membership.alias,
      id: membership.id || known.id,
      name: membership.name || known.name,
    };
  });
}

export default function TenantSelectPage() {
  const loggedIn = isLoggedIn();
  const tokenOrganizations = getOrganizationMemberships();
  const organizationMembershipsKey = JSON.stringify(tokenOrganizations);
  const [organizations, setOrganizations] = useState<OrganizationMembership[]>(
    () => tokenOrganizations,
  );
  const [directoryResolved, setDirectoryResolved] = useState(() => !loggedIn);
  const [directoryFailed, setDirectoryFailed] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  const autoFinalizeStarted = useRef(false);
  const autoSignInStarted = useRef(false);
  // Seeded from tokenOrganizations (not left `null` until an effect runs) so
  // <Select> is controlled from its very first render — starting `undefined`
  // and flipping to a string once an effect sets it trips React's "Select is
  // changing from uncontrolled to controlled" warning.
  const [selectedAlias, setSelectedAlias] = useState<string | null>(() =>
    tokenOrganizations.length > 1 ? tokenOrganizations[0].alias : null,
  );

  useEffect(() => {
    setOrganizations(tokenOrganizations);
    // tokenOrganizations is rebuilt each render; the JSON key is the actual dependency.
  }, [organizationMembershipsKey]);

  useEffect(() => {
    // Skip the realm-chooser page entirely: send logged-out visitors straight
    // to Keycloak's shared "m8flow" realm login. Platform admins reach the
    // master realm via the "Platform Admin Sign In" link Keycloak's own login
    // page renders (see keycloak/themes/m8flow/login/login.ftl +
    // masterRealmLogin.js), which reuses the redirect_url/state this call sets.
    if (loggedIn || autoSignInStarted.current) {
      return;
    }
    autoSignInStarted.current = true;
    clearSelectedTenantCookie();
    login({ redirectUrl: designerRootUrl() });
  }, [loggedIn]);

  useEffect(() => {
    if (!loggedIn) {
      setDirectoryResolved(true);
      return;
    }

    // Always resolve the real directory: the JWT's `organization` claim only
    // ever carries the single "active" org (RealmInfoMapper), never the full
    // membership list, so its length can never be trusted to decide
    // auto-finalize vs. show-selector for a multi-tenant user.
    let ignore = false;
    fetchOrganizationMemberships()
      .then((resolved) => {
        if (ignore) {
          return;
        }
        setOrganizations(mergeOrganizationMemberships(tokenOrganizations, resolved));
        setDirectoryFailed(false);
        setDirectoryResolved(true);
      })
      .catch(() => {
        if (ignore) {
          return;
        }
        // Directory unreachable: the JWT's `organization` claim carries only
        // the single active org, so it cannot stand in for the membership
        // list here. Surface the failure and let the user retry rather than
        // auto-finalizing them into a possibly-stale tenant that would then
        // take a full logout to escape.
        setDirectoryFailed(true);
        setDirectoryResolved(true);
      });

    return () => {
      ignore = true;
    };
  }, [loggedIn, organizationMembershipsKey, retryNonce]);

  useEffect(() => {
    if (
      !loggedIn ||
      !directoryResolved ||
      directoryFailed ||
      organizations.length !== 1 ||
      autoFinalizeStarted.current
    ) {
      return;
    }
    autoFinalizeStarted.current = true;
    finalizeTenantLogin(organizations[0]);
  }, [loggedIn, directoryResolved, directoryFailed, organizations]);

  useEffect(() => {
    if (!loggedIn || organizations.length < 2) {
      return;
    }
    if (!selectedAlias || !organizations.some((organization) => organization.alias === selectedAlias)) {
      setSelectedAlias(organizations[0].alias);
    }
  }, [loggedIn, organizations, selectedAlias]);

  if (!loggedIn) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <p className="text-sm text-muted-foreground" data-testid="sign-in-redirecting">
          Redirecting to sign in…
        </p>
      </main>
    );
  }

  if (!directoryResolved) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <p className="text-sm text-muted-foreground" data-testid="tenant-membership-loading">
          Checking organization membership…
        </p>
      </main>
    );
  }

  if (directoryFailed) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <div className="w-full max-w-md space-y-6">
          <div className="space-y-2">
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Couldn&rsquo;t load your tenants
            </h1>
            <p className="rounded-lg border border-border bg-card px-4 py-3 text-sm">
              We couldn&rsquo;t confirm which organizations you belong to.
            </p>
            <p className="text-sm text-muted-foreground" data-testid="tenant-directory-error">
              Retry in a moment. If this keeps happening, contact an administrator.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="pill"
              size="pill"
              onClick={() => {
                setDirectoryFailed(false);
                setDirectoryResolved(false);
                setRetryNonce((nonce) => nonce + 1);
              }}
              data-testid="tenant-directory-retry-button"
              className="bg-primary text-primary-foreground hover:bg-primary/80"
            >
              Retry
            </Button>
            <Button type="button" variant="ghost" onClick={() => logout()} data-testid="back-to-login-button">
              Back to login
            </Button>
          </div>
        </div>
      </main>
    );
  }

  if (organizations.length === 0) {
    const currentUser = getCurrentUser();
    const signedInAs = currentUser?.email || currentUser?.username;
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <div className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="h-1 bg-primary" />
          <div className="space-y-6 p-8">
            <div className="flex size-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Building2 className="size-5" aria-hidden="true" />
            </div>
            <div className="space-y-3">
              <h1 className="font-display text-3xl font-semibold tracking-tight">No Tenants Available</h1>
              <p className="text-sm text-muted-foreground" data-testid="no-tenant-access-message">
                This account isn&apos;t a member of any organization yet. Contact an administrator to be
                added to a tenant, then sign in again.
              </p>
            </div>
            {signedInAs ? (
              <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                <Info className="size-4 shrink-0" aria-hidden="true" />
                <span>
                  Signed in as <span className="font-mono text-foreground">{signedInAs}</span>
                </span>
              </div>
            ) : null}
            <Button
              type="button"
              className="w-full text-xs font-semibold uppercase tracking-wider sm:w-auto"
              onClick={() => logout()}
              data-testid="back-to-login-button"
            >
              Back to login
            </Button>
          </div>
        </div>
      </main>
    );
  }

  if (organizations.length === 1) {
    const tenant = organizations[0];
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <div className="w-full max-w-md space-y-2">
          <h1 className="font-display text-2xl font-semibold tracking-tight">Finalizing tenant access</h1>
          <p className="text-sm text-muted-foreground">
            Continuing into {tenant.name || tenant.alias}…
          </p>
        </div>
      </main>
    );
  }

  const selectedOrganization =
    organizations.find((organization) => organization.alias === selectedAlias) ?? organizations[0];

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
      <div className="w-full max-w-md space-y-6 rounded-2xl border-t-4 border-t-primary bg-card p-8 shadow-lg">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight">Select a Tenant</h1>
          <p className="text-sm text-muted-foreground">Choose the organization you want to work in.</p>
        </div>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold tracking-[0.04em] text-muted-foreground uppercase">
              Tenant
            </label>
            <Select value={selectedOrganization?.alias} onValueChange={setSelectedAlias}>
              <SelectTrigger
                data-testid="tenant-select-trigger"
                className="border-primary focus:border-primary focus:ring-primary/50"
              >
                <SelectValue placeholder="Select an organization" />
              </SelectTrigger>
              <SelectContent>
                {organizations.map((organization) => {
                  const displayName = organization.name || organization.alias;
                  const showAlias = displayName !== organization.alias;
                  return (
                    <SelectItem
                      key={organization.alias}
                      value={organization.alias}
                      data-testid={`organization-option-${organization.alias}`}
                    >
                      {displayName}
                      {showAlias ? ` (${organization.alias})` : ''}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="flex justify-end">
            <Button
              type="button"
              variant="pill"
              size="pill"
              disabled={!selectedOrganization}
              onClick={() => selectedOrganization && finalizeTenantLogin(selectedOrganization)}
              data-testid="tenant-select-confirm-button"
              className="bg-primary text-primary-foreground hover:bg-primary/80"
            >
              Continue
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}

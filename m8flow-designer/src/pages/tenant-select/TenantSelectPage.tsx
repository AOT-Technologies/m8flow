import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { fetchOrganizationMemberships } from '@/lib/api';
import {
  clearSelectedTenantCookie,
  finalizeTenantLogin,
  getOrganizationMemberships,
  isLoggedIn,
  login,
  logout,
  type OrganizationMembership,
} from '@/lib/auth';

function designerRootUrl(): string {
  return `${window.location.origin}/`;
}

function mergeOrganizationMemberships(
  currentMemberships: OrganizationMembership[],
  resolvedMemberships: OrganizationMembership[],
): OrganizationMembership[] {
  const resolvedByKey = new Map<string, OrganizationMembership>();
  for (const membership of resolvedMemberships) {
    if (membership.id) {
      resolvedByKey.set(`id:${membership.id}`, membership);
    }
    resolvedByKey.set(`alias:${membership.alias}`, membership);
  }

  return currentMemberships.map((membership) => {
    const resolved =
      (membership.id && resolvedByKey.get(`id:${membership.id}`)) ||
      resolvedByKey.get(`alias:${membership.alias}`);
    if (!resolved) {
      return membership;
    }
    return {
      alias: membership.alias,
      id: resolved.id || membership.id,
      name: resolved.name || membership.name,
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
  const [directoryResolved, setDirectoryResolved] = useState(
    () => !loggedIn || tokenOrganizations.length > 0,
  );
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

    const needsDirectory =
      tokenOrganizations.length === 0 ||
      tokenOrganizations.some((organization) => !organization.name?.trim());
    if (!needsDirectory) {
      setDirectoryResolved(true);
      return;
    }

    let ignore = false;
    fetchOrganizationMemberships()
      .then((resolved) => {
        if (ignore) {
          return;
        }
        if (tokenOrganizations.length === 0) {
          setOrganizations(resolved);
        } else {
          setOrganizations(mergeOrganizationMemberships(tokenOrganizations, resolved));
        }
        setDirectoryResolved(true);
      })
      .catch(() => {
        if (ignore) {
          return;
        }
        setOrganizations(tokenOrganizations);
        setDirectoryResolved(true);
      });

    return () => {
      ignore = true;
    };
  }, [loggedIn, organizationMembershipsKey]);

  useEffect(() => {
    if (!loggedIn || !directoryResolved || organizations.length !== 1 || autoFinalizeStarted.current) {
      return;
    }
    autoFinalizeStarted.current = true;
    finalizeTenantLogin(organizations[0]);
  }, [loggedIn, directoryResolved, organizations]);

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

  if (organizations.length === 0 && !directoryResolved) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <p className="text-sm text-muted-foreground" data-testid="tenant-membership-loading">
          Checking organization membership…
        </p>
      </main>
    );
  }

  if (organizations.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6 text-foreground">
        <div className="w-full max-w-md space-y-6">
          <div className="space-y-2">
            <h1 className="font-display text-3xl font-semibold tracking-tight">No tenants available</h1>
            <p className="rounded-lg border border-border bg-card px-4 py-3 text-sm">
              This account is not a member of any organization.
            </p>
            <p className="text-sm text-muted-foreground" data-testid="no-tenant-access-message">
              Contact an administrator to be added to a tenant, then sign in again.
            </p>
          </div>
          <Button type="button" variant="ghost" onClick={() => logout()} data-testid="back-to-login-button">
            Back to login
          </Button>
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
      <div className="w-full max-w-md space-y-6">
        <div className="space-y-2">
          <h1 className="font-display text-3xl font-semibold tracking-tight">Select a tenant</h1>
          <p className="text-sm text-muted-foreground">Choose the organization you want to work in.</p>
        </div>
        <div className="space-y-4">
          <Select value={selectedAlias ?? undefined} onValueChange={setSelectedAlias}>
            <SelectTrigger data-testid="tenant-select-trigger">
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
          <div className="flex justify-end">
            <Button
              type="button"
              disabled={!selectedOrganization}
              onClick={() => selectedOrganization && finalizeTenantLogin(selectedOrganization)}
              data-testid="tenant-select-confirm-button"
            >
              Continue
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}

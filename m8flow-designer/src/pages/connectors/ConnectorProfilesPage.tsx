import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Plus } from 'lucide-react';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
  connectorsErrorMessage,
  deactivateConnectorProfile,
  deleteConnectorProfile,
  fetchConnectorProfiles,
  fetchConnectorTemplate,
  updateConnectorProfile,
  type ConnectorProfile,
  type ConnectorTemplate,
} from '@/lib/connectorsApi';

import { ConnectorsGate, useConnectorsContext } from './ConnectorsGate';

const TITLE = 'Connector profiles';

export default function ConnectorProfilesPage() {
  return (
    <ConnectorsGate title={TITLE} requireTenant>
      <ConnectorProfilesBody />
    </ConnectorsGate>
  );
}

function ConnectorProfilesBody() {
  const { connectorId = '' } = useParams();
  const navigate = useNavigate();
  const { scopedTenantId, canManageConnectorProfiles } = useConnectorsContext();
  const [template, setTemplate] = useState<ConnectorTemplate | null>(null);
  const [profiles, setProfiles] = useState<ConnectorProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ConnectorProfile | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [loadedTemplate, loadedProfiles] = await Promise.all([
        fetchConnectorTemplate(connectorId),
        fetchConnectorProfiles({
          connectorType: connectorId,
          tenantId: scopedTenantId,
        }),
      ]);
      setTemplate(loadedTemplate);
      setProfiles(loadedProfiles);
    } catch (err: unknown) {
      setError(connectorsErrorMessage(err, 'Could not load profiles.'));
      setTemplate(null);
      setProfiles([]);
    } finally {
      setLoading(false);
    }
  }, [connectorId, scopedTenantId]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const ordered = useMemo(
    () =>
      [...profiles].sort((a, b) => {
        if (a.is_active !== b.is_active) {
          return a.is_active ? -1 : 1;
        }
        return a.profile_name.localeCompare(b.profile_name);
      }),
    [profiles],
  );

  async function runAction(action: () => Promise<unknown>) {
    setActionError(null);
    try {
      await action();
      setReloadKey((key) => key + 1);
    } catch (err: unknown) {
      setActionError(connectorsErrorMessage(err, 'Could not update the profile.'));
    }
  }

  const heading = template?.name ? `${template.name} profiles` : TITLE;

  const columns: DataTableColumn<ConnectorProfile>[] = [
    {
      key: 'profile',
      header: 'Profile',
      width: 'minmax(200px,2fr)',
      render: (profile) => (
        <div>
          <div className={cn('font-medium text-foreground', !profile.is_active && 'opacity-55')}>
            {profile.display_name}
          </div>
          {!profile.is_active ? (
            <span className="mt-1 inline-block text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
              Inactive
            </span>
          ) : null}
          {profile.description ? (
            <div
              className={cn(
                'mt-1 text-[13px] text-muted-foreground',
                !profile.is_active && 'opacity-55',
              )}
            >
              {profile.description}
            </div>
          ) : null}
        </div>
      ),
    },
    {
      key: 'identifier',
      header: 'Identifier',
      width: 'minmax(140px,1fr)',
      render: (profile) => (
        <span
          className={cn(
            'font-mono text-[13px] text-muted-foreground',
            !profile.is_active && 'opacity-55',
          )}
        >
          {profile.profile_name}
        </span>
      ),
    },
    {
      key: 'credentials',
      header: 'Credentials',
      width: 'minmax(160px,1.4fr)',
      render: (profile) => (
        <span className={cn('text-muted-foreground', !profile.is_active && 'opacity-55')}>
          {profile.configured_secrets.length ? profile.configured_secrets.join(', ') : 'None stored'}
        </span>
      ),
    },
    ...(canManageConnectorProfiles
      ? [
          {
            key: 'actions',
            header: <span className="sr-only">Actions</span>,
            className: 'text-right',
            width: 'minmax(180px,1fr)',
            render: (profile) => (
              <div className="flex flex-wrap justify-end gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    navigate(
                      `/connectors/${encodeURIComponent(connectorId)}/profiles/${profile.id}/edit`,
                    )
                  }
                >
                  Edit
                </Button>
                {profile.is_active ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      void runAction(() => deactivateConnectorProfile(profile.id, scopedTenantId))
                    }
                  >
                    Deactivate
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      void runAction(() =>
                        updateConnectorProfile(profile.id, { is_active: true }, scopedTenantId),
                      )
                    }
                  >
                    Reactivate
                  </Button>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setPendingDelete(profile)}
                >
                  Delete
                </Button>
              </div>
            ),
          } satisfies DataTableColumn<ConnectorProfile>,
        ]
      : []),
  ];

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 text-sm text-muted-foreground">
            <Link to="/connectors" className="hover:underline">
              Connectors
            </Link>
          </p>
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{heading}</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Saved credential sets a Service Task can select by name.
          </p>
        </div>
        {canManageConnectorProfiles ? (
          <Button asChild variant="pill-dark" size="pill">
            <Link to={`/connectors/${encodeURIComponent(connectorId)}/profiles/new`}>
              <Plus className="size-3.5" aria-hidden />
              Add profile
            </Link>
          </Button>
        ) : null}
      </div>

      {error ? <Alert tone="error" className="mb-4">{error}</Alert> : null}
      {actionError ? <Alert tone="error" className="mb-4">{actionError}</Alert> : null}

      <Card variant="bordered" className="overflow-hidden">
        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">Loading profiles…</p>
        ) : ordered.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground" data-testid="connector-profiles-empty">
            No profiles yet. Add one to select it from a Service Task.
          </p>
        ) : (
          <DataTable columns={columns} rows={ordered} getRowKey={(profile) => profile.id} />
        )}
      </Card>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this profile permanently?"
        description={
          <>
            This removes "{pendingDelete?.display_name ?? ''}" and its stored credentials. Any
            process model that still selects this profile will fail when it runs. Deactivate
            instead if you may need it again.
          </>
        }
        confirmLabel="Delete"
        onConfirm={() => {
          const target = pendingDelete;
          setPendingDelete(null);
          if (target) {
            void runAction(() => deleteConnectorProfile(target.id, scopedTenantId));
          }
        }}
      />
    </main>
  );
}

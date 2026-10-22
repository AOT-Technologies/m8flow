import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Plus } from 'lucide-react';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { formatRelativeTimeVerbose } from '@/lib/relativeTime';
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
import { ConnectorsBackButton } from './ConnectorsBackButton';

export default function ConnectorProfilesPage() {
  const { t } = useTranslation();
  return (
    <ConnectorsGate title={t('connectors.profilesTitle')}>
      <ConnectorProfilesBody />
    </ConnectorsGate>
  );
}

function ConnectorProfilesBody() {
  const { t } = useTranslation();
  const { connectorId = '' } = useParams();
  const navigate = useNavigate();
  const { scopedTenantId, canCreateConnectorProfiles, canUpdateConnectorProfiles, canDeleteConnectorProfiles } = useConnectorsContext();
  const { allTenants } = useConnectorsContext();
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
      setError(connectorsErrorMessage(err, t('connectors.errors.loadProfiles')));
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
      setActionError(connectorsErrorMessage(err, t('connectors.errors.updateProfile')));
    }
  }

  const heading = template?.name
    ? t('connectors.profilesNamed', { name: template.name })
    : t('connectors.profilesTitle');

  const columns: DataTableColumn<ConnectorProfile>[] = [
    {
      key: 'profile',
      header: t('connectors.profiles.columns.profile'),
      width: 'minmax(200px,2fr)',
      render: (profile) => (
        <div>
          <div className={cn('font-medium text-foreground', !profile.is_active && 'opacity-55')}>
            {profile.display_name}
          </div>
          {!profile.is_active ? (
            <span className="mt-1 inline-block text-[11px] tracking-[0.06em] text-muted-foreground uppercase">
              {t('connectors.profiles.inactive')}
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
      header: t('connectors.identifier'),
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
      key: 'status',
      header: t('connectors.profiles.columns.status'),
      width: 'minmax(160px,1.4fr)',
      render: (profile) => {
        const missing = (template?.profileFields ?? []).filter(
          (field) => field.required && !profile.configured_secrets.includes(field.id),
        );
        return (
          <div className={cn(!profile.is_active && 'opacity-55')}>
            <Badge variant={missing.length ? 'warning' : 'success'}>
              {missing.length ? 'Incomplete' : 'Configured'}
            </Badge>
            {missing.length ? (
              <div className="mt-1 text-[13px] text-muted-foreground">
                Missing: {missing.map((field) => field.label).join(', ')}
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      key: 'updated',
      header: 'Last updated',
      width: 'minmax(120px,1fr)',
      render: (profile) => (
        <span
          className={cn('text-[13px] text-muted-foreground', !profile.is_active && 'opacity-55')}
          title={
            profile.updated_at && !Number.isNaN(Date.parse(profile.updated_at))
              ? new Date(profile.updated_at).toLocaleString()
              : undefined
          }
        >
          {formatRelativeTimeVerbose(profile.updated_at)}
        </span>
      ),
    },
    ...(canUpdateConnectorProfiles || canDeleteConnectorProfiles
      ? [
          {
            key: 'actions',
            header: <span className="sr-only">{t('common.actions')}</span>,
            className: 'text-right',
            width: 'minmax(180px,1fr)',
            render: (profile) => (
              <div className="flex flex-wrap justify-end gap-1">
                {canUpdateConnectorProfiles ? <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    navigate(
                      `/connectors/${encodeURIComponent(connectorId)}/profiles/${profile.id}/edit`,
                    )
                  }
                >
                  {t('connectors.profiles.edit')}
                </Button> : null}
                {profile.is_active && canDeleteConnectorProfiles ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      void runAction(() => deactivateConnectorProfile(profile.id, scopedTenantId))
                    }
                  >
                    {t('connectors.profiles.deactivate')}
                  </Button>
                ) : !profile.is_active && canUpdateConnectorProfiles ? (
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
                    {t('connectors.profiles.reactivate')}
                  </Button>
                ) : null}
                {canDeleteConnectorProfiles ? <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setPendingDelete(profile)}
                >
                  {t('common.delete')}
                </Button> : null}
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
          <ConnectorsBackButton label={t('connectors.title')} to="/connectors" />
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{heading}</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            {t('connectors.profiles.subtitle')}
          </p>
        </div>
        {canCreateConnectorProfiles ? (
          <Button asChild variant="pill-dark" size="pill">
            <Link to={`/connectors/${encodeURIComponent(connectorId)}/profiles/new`}>
              <Plus className="size-3.5" aria-hidden />
              {t('connectors.addProfile')}
            </Link>
          </Button>
        ) : null}
      </div>

      {error ? <Alert tone="error" className="mb-4">{error}</Alert> : null}
      {actionError ? <Alert tone="error" className="mb-4">{actionError}</Alert> : null}

      <Card variant="bordered" className="overflow-hidden">
        {loading ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground">{t('connectors.profiles.loading')}</p>
        ) : ordered.length === 0 ? (
          <p className="px-[22px] py-6 text-sm text-muted-foreground" data-testid="connector-profiles-empty">
            {allTenants
              ? t('connectors.profiles.emptyAllTenants')
              : canCreateConnectorProfiles || canUpdateConnectorProfiles
                ? t('connectors.profiles.emptyManage')
                : t('connectors.profiles.emptyReadOnly')}
          </p>
        ) : (
          <DataTable columns={columns} rows={ordered} getRowKey={(profile) => profile.id} />
        )}
      </Card>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title={t('connectors.profiles.deleteTitle')}
        description={t('connectors.profiles.deleteDescription', {
          name: pendingDelete?.display_name ?? '',
        })}
        confirmLabel={t('common.delete')}
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

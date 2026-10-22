import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { fetchConnectorsGrouped, type ConnectorGroup } from '@/lib/api';
import { connectorsErrorMessage } from '@/lib/connectorsApi';
import { Alert } from '@/components/library/alert/Alert';
import { EmptyState } from '@/components/library/empty-state/EmptyState';
import { Modal } from '@/components/library/modal/Modal';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

import { ConnectorsGate, useConnectorsContext } from './ConnectorsGate';

export default function ConnectorsPage() {
  const { t } = useTranslation();
  return (
    <ConnectorsGate title={t('connectors.title')}>
      <ConnectorsBody />
    </ConnectorsGate>
  );
}

function ConnectorsBody() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { canConfigureProfiles, canConfigureSecrets } = useConnectorsContext();
  const [groups, setGroups] = useState<ConnectorGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [operationsFor, setOperationsFor] = useState<ConnectorGroup | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchConnectorsGrouped()
      .then((payload) => {
        if (!cancelled) {
          setGroups(Array.isArray(payload) ? payload : []);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(connectorsErrorMessage(err, t('connectors.errors.loadConnectors')));
          setGroups([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) {
      return groups;
    }
    return groups.filter((group) => {
      if (group.name.toLowerCase().includes(term)) {
        return true;
      }
      if ((group.description || '').toLowerCase().includes(term)) {
        return true;
      }
      return group.operations.some(
        (operation) =>
          operation.name.toLowerCase().includes(term) ||
          operation.id.toLowerCase().includes(term),
      );
    });
  }, [groups, search]);

  function configure(group: ConnectorGroup) {
    if (group.supportsProfiles) {
      navigate(`/connectors/${encodeURIComponent(group.id)}/profiles`);
      return;
    }
    navigate('/configuration/secrets');
  }

  return (
    <main className="flex-1 px-11 py-10" data-testid="connectors-page">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{t('connectors.title')}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          {t('connectors.catalog.subtitle')}
        </p>
      </div>

      {error ? (
        <Alert tone="error" className="mb-4">
          {error}
        </Alert>
      ) : null}

      {!loading && groups.length > 0 ? (
        <div className="mb-6 max-w-md">
          <SearchBar
            value={search}
            onChange={setSearch}
            placeholder={t('connectors.catalog.searchPlaceholder')}
            aria-label={t('connectors.catalog.searchLabel')}
            data-testid="connectors-search"
          />
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">{t('connectors.catalog.loading')}</p>
      ) : groups.length === 0 ? (
        <EmptyState
          title={t('connectors.catalog.emptyTitle')}
          description={t('connectors.catalog.emptyDescription')}
          data-testid="connectors-empty"
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title={t('connectors.catalog.noMatchTitle')}
          description={t('connectors.catalog.noMatchDescription')}
          data-testid="connectors-no-match"
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((group) => (
            <Card
              key={group.id}
              variant="bordered"
              className="flex flex-col p-[22px]"
              data-testid={`connector-card-${group.id}`}
            >
              <div className="mb-3 flex items-center gap-3">
                <span
                  aria-hidden
                  className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted text-sm font-semibold text-foreground"
                >
                  {(group.name || group.id).slice(0, 1).toUpperCase()}
                </span>
                <h2
                  className="min-w-0 text-[17px] font-semibold tracking-tight"
                  data-testid={`connector-name-${group.id}`}
                >
                  {group.name}
                </h2>
              </div>
              <div className="mb-3 flex flex-wrap gap-1.5">
                <Badge variant="outline" data-testid={`connector-op-count-${group.id}`}>
                  {t('connectors.catalog.operationCount', { count: group.operationCount })}
                </Badge>
                <Badge variant="success">{t('connectors.catalog.available')}</Badge>
              </div>
              <p
                className="mb-5 flex-1 text-sm text-muted-foreground"
                data-testid={`connector-description-${group.id}`}
              >
                {group.description || t('connectors.catalog.defaultDescription')}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="pill-outline"
                  size="pill"
                  onClick={() => setOperationsFor(group)}
                  data-testid={`connector-view-ops-${group.id}`}
                >
                  {t('connectors.catalog.viewOperations')}
                </Button>
                {(group.supportsProfiles ? canConfigureProfiles : canConfigureSecrets) ? (
                  <Button
                    type="button"
                    variant="pill-outline"
                    size="pill"
                    onClick={() => configure(group)}
                    data-testid={`connector-configure-${group.id}`}
                  >
                    Configure
                  </Button>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}

      <ConnectorOperationsDialog
        connector={operationsFor}
        onClose={() => setOperationsFor(null)}
      />
    </main>
  );
}

function ConnectorOperationsDialog({
  connector,
  onClose,
}: {
  connector: ConnectorGroup | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Modal
      open={connector !== null}
      onOpenChange={(open) => !open && onClose()}
      title={
        connector
          ? t('connectors.operations.titleNamed', { name: connector.name })
          : t('connectors.operations.title')
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        {t('connectors.operations.subtitle')}
      </p>
      {connector && connector.operations.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('connectors.operations.empty')}</p>
      ) : (
        <ul className="max-h-[60vh] space-y-3 overflow-y-auto">
          {connector?.operations.map((operation) => (
            <li
              key={operation.id}
              className="rounded-lg border border-border px-3 py-2.5"
              data-testid={`connector-operation-${operation.id}`}
            >
              <div className="font-medium text-foreground">{operation.name || operation.id}</div>
              <div className="mt-0.5 font-mono text-[12px] text-muted-foreground">{operation.id}</div>
              {operation.description ? (
                <p className="mt-1 text-sm text-muted-foreground">{operation.description}</p>
              ) : null}
              {operation.parameters.length > 0 ? (
                <ul className="mt-2 space-y-0.5 text-[12.5px] text-muted-foreground">
                  {operation.parameters.map((parameter) => (
                    <li key={parameter.id}>
                      <span className="font-mono">{parameter.id}</span>
                      {parameter.type ? ` · ${parameter.type}` : ''}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { fetchNatsEmailStatus, type NatsEmailStatus } from '@/lib/secretsApi';

/**
 * The tenant's NATS email status. `enabled` must be false without /secrets read (403) or
 * without one tenant (400). `failed` is true when the status could not be read.
 */
export function useNatsEmailStatus({
  tenantId,
  enabled,
  reloadKey = 0,
}: {
  tenantId: string | null;
  enabled: boolean;
  reloadKey?: number;
}) {
  const [status, setStatus] = useState<NatsEmailStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const scope = `${enabled}:${tenantId ?? ''}`;
  const lastScope = useRef(scope);

  useEffect(() => {
    // A reload keeps showing the last status until the new one arrives, so the reminder
    // doesn't flicker; a different tenant (or losing access) starts from nothing.
    if (lastScope.current !== scope || !enabled) {
      lastScope.current = scope;
      setStatus(null);
      setFailed(false);
    }
    if (!enabled) return;
    let cancelled = false;
    fetchNatsEmailStatus(tenantId)
      .then((next) => {
        if (cancelled) return;
        setStatus(next);
        setFailed(false);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, enabled, reloadKey]);

  return { status, failed };
}

/**
 * Tells a tenant when the NATS notification worker cannot email external-form links
 * because NATS_SMTP_* configuration variables are missing or unreadable. Renders nothing
 * until the status is known, or once it is configured: the worker parks those emails and
 * sends them once this is fixed.
 */
export function NatsEmailSetupNotice({ status }: { status: NatsEmailStatus | null }) {
  const { t } = useTranslation();

  if (!status || status.configured) return null;

  const keyList = (keys: string[]) =>
    keys.map((key) => (
      <code key={key} className="font-mono text-xs">
        {key}
      </code>
    ));

  return (
    <Alert tone={status.waitingCount > 0 ? 'warning' : 'info'} className="mb-4" data-testid="nats-email-setup">
      <div className="space-y-1.5 text-sm">
        <p className="font-semibold text-foreground">{t('configuration.natsEmail.title')}</p>
        <p className="text-muted-foreground">{t('configuration.natsEmail.body')}</p>
        {status.waitingCount > 0 ? (
          <p className="text-foreground" data-testid="nats-email-waiting">
            {t('configuration.natsEmail.waiting', { count: status.waitingCount })}
          </p>
        ) : null}
        {status.missingKeys.length > 0 ? (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{t('configuration.natsEmail.missing')}</span>
            {keyList(status.missingKeys)}
          </p>
        ) : null}
        {status.unreadableKeys.length > 0 ? (
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{t('configuration.natsEmail.unreadable')}</span>
            {keyList(status.unreadableKeys)}
          </p>
        ) : null}
      </div>
    </Alert>
  );
}

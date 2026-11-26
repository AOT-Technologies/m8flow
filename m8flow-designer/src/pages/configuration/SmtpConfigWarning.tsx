import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { useCapabilities } from '@/components/session/hooks';
import { fetchSmtpStatus, type SmtpStatus } from '@/lib/externalFormNotificationsApi';

/**
 * Warns when the tenant cannot send external-form emails because its NATS_SMTP_*
 * settings are missing or unreadable, and names them. Renders nothing when the
 * settings are usable, the status cannot be read, or the caller lacks /secrets read
 * (the status endpoint's grant). A super-admin needs a concrete tenant selected.
 */
export function SmtpConfigWarning({ tenantId, isSuperAdmin }: { tenantId: string | null; isSuperAdmin: boolean }) {
  const { t } = useTranslation();
  const { canReadSecrets } = useCapabilities();
  const [status, setStatus] = useState<SmtpStatus | null>(null);
  const enabled = canReadSecrets && (!isSuperAdmin || Boolean(tenantId));

  useEffect(() => {
    setStatus(null);
    if (!enabled) return;
    let cancelled = false;
    fetchSmtpStatus(isSuperAdmin ? tenantId : null)
      .then((result) => {
        if (!cancelled) setStatus(result);
      })
      // A warning is advisory: if the status can't be read, show nothing rather than an error.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [enabled, isSuperAdmin, tenantId]);

  if (!status || status.configured) return null;

  const unreadable = new Set(status.unreadable_keys);
  const missing = status.missing_required_keys.filter((key) => !unreadable.has(key));
  return (
    <Alert tone="warning" className="mb-4" data-testid="smtp-config-warning">
      <span className="block font-medium">{t('configuration.smtpWarning.title')}</span>
      {missing.length ? <span className="block">{t('configuration.smtpWarning.missing', { keys: missing.join(', ') })}</span> : null}
      {unreadable.size ? (
        <span className="block">{t('configuration.smtpWarning.unreadable', { keys: [...unreadable].join(', ') })}</span>
      ) : null}
    </Alert>
  );
}

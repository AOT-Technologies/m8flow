import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useRouteError } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Button } from '@/components/ui/button';
import { isNetworkFailure } from '@/lib/networkErrors';
import { useOnline } from '@/lib/useOnline';

/** App-wide notice while the browser is offline; pages stay mounted, so typed input survives. */
export function OfflineBanner() {
  const { t } = useTranslation();
  if (useOnline()) return null;
  return (
    <div className="fixed inset-x-0 top-3 z-50 mx-auto w-fit max-w-[calc(100%-2rem)] rounded-[10px] bg-background shadow-md">
      <Alert tone="warning">{t('shell.network.offline')}</Alert>
    </div>
  );
}

/** Router errorElement: a friendly message and Retry instead of React Router's developer error page. */
export function RouteError() {
  const { t } = useTranslation();
  const error = useRouteError();
  const online = useOnline();
  const wasOnline = useRef(online);
  const reloaded = useRef(false);
  const networkFailure = isNetworkFailure(error);

  // React.lazy caches rejected imports. Reload once on reconnection; never
  // reload on mount, duplicate online events, or an unrelated application bug.
  useEffect(() => {
    const reconnected = !wasOnline.current && online;
    wasOnline.current = online;
    if (networkFailure && reconnected && !reloaded.current) {
      reloaded.current = true;
      window.location.reload();
    }
  }, [online, networkFailure]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-6 text-foreground">
      <Alert tone="error">
        {networkFailure ? t('shell.network.unableToConnect') : t('shell.network.pageFailed')}
      </Alert>
      <Button onClick={() => window.location.reload()}>{t('shell.network.retry')}</Button>
    </main>
  );
}

import { useEffect, useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { useRouteError } from 'react-router-dom';

import { Alert } from '@/components/library/alert/Alert';
import { Button } from '@/components/ui/button';
import { NetworkError } from '@/lib/api';

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange);
  window.addEventListener('offline', onChange);
  return () => {
    window.removeEventListener('online', onChange);
    window.removeEventListener('offline', onChange);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, () => navigator.onLine);
}

// Chrome, Firefox, Safari and Vite wordings for a request or page chunk that never arrived.
const NETWORK_FAILURE = /failed to fetch|dynamically imported module|importing a module script failed|unable to preload|networkerror/i;

export function isNetworkFailure(error: unknown): boolean {
  return error instanceof NetworkError || (error instanceof Error && NETWORK_FAILURE.test(error.message));
}

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

  // React.lazy caches a failed page chunk, so retrying means reloading; do it by itself once back online.
  useEffect(() => {
    const reload = () => window.location.reload();
    window.addEventListener('online', reload);
    return () => window.removeEventListener('online', reload);
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-6 text-foreground">
      <Alert tone="error">
        {!online || isNetworkFailure(error) ? t('shell.network.unableToConnect') : t('shell.network.pageFailed')}
      </Alert>
      <Button onClick={() => window.location.reload()}>{t('shell.network.retry')}</Button>
    </main>
  );
}

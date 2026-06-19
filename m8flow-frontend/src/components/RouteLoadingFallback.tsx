import { useTranslation } from 'react-i18next';

export function RouteLoadingFallback() {
  const { t } = useTranslation();
  return (
    <div
      style={{
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        minHeight: 240,
        width: '100%',
      }}
      aria-label={t('loading')}
    >
      {t('loading')}…
    </div>
  );
}


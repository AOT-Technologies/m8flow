import { Mail } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Card } from '@/components/ui/card';

export default function MessagesPage() {
  const { t } = useTranslation();
  return (
    <main className="flex-1 px-11 py-10" data-testid="messages-page">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{t('messages.title')}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          {t('messages.description')}
        </p>
      </div>

      <Card variant="bordered" className="max-w-3xl p-6">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted text-primary">
            <Mail className="size-5" aria-hidden />
          </span>
          <div>
            <h2 className="text-lg font-semibold">{t('messages.inbox.title')}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t('messages.inbox.empty')}</p>
          </div>
        </div>
      </Card>
    </main>
  );
}

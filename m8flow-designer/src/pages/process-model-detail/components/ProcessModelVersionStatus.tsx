import { useTranslation } from 'react-i18next';

import { Pill } from '@/components/library/pill/Pill';
import { processModelStatusToPillProps } from '@/components/library/pill/processModelStatusToPillProps';
import type { ProcessModelStatus, ProcessModelVersionState } from '@/lib/api';
import { cn } from '@/lib/utils';

export function ProcessModelVersionStatus({
  status, published_version: published, draft_version: draft, has_unpublished_changes: pending, stacked = false,
}: ProcessModelVersionState & { status: ProcessModelStatus | null | undefined; stacked?: boolean }) {
  const { t } = useTranslation();
  const { children: label, ...statusPill } = processModelStatusToPillProps(status, pending);
  const pillClass = 'max-w-full shrink whitespace-normal [overflow-wrap:anywhere]';
  return (
    <span className={cn('inline-flex max-w-full flex-wrap gap-1.5', stacked ? 'flex-col items-start' : 'items-center')}>
      <Pill {...statusPill} className={pillClass}>{label}</Pill>
      {(published != null || draft != null) && (
        <span className="flex min-w-0 max-w-full flex-wrap items-center gap-1.5">
          {published != null && <Pill tone="muted" className={pillClass}>{t('common.modelVersions.published', { version: published })}</Pill>}
          {draft != null && <Pill tone="muted" className={pillClass}>{t('common.modelVersions.draft', { version: draft })}</Pill>}
        </span>
      )}
    </span>
  );
}

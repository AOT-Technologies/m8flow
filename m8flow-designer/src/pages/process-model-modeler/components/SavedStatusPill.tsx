import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

import { Pill, type PillProps } from '@/components/library/pill/Pill';

export type SaveStatus = 'saving' | 'saved' | 'error';

const TONE: Record<SaveStatus, NonNullable<PillProps['tone']>> = {
  saving: 'muted',
  saved: 'success',
  error: 'error',
};

const LABEL_KEYS: Record<SaveStatus, ParseKeys> = {
  saving: 'modeler.saving',
  saved: 'modeler.saveStatus.saved',
  error: 'modeler.saveStatus.failed',
};

/**
 * The pill and the Save button (SaveButton.tsx) are never shown together —
 * decided on the manual-save ticket: dirty state shows the Save button;
 * clean/saving/error states show this pill. "error" is a brief flash
 * (timed by the page) before reverting to the Save button, not a
 * persistent state.
 *
 * Thin wrapper around `library/pill` `Pill` (component-adoption map,
 * ticket 08) — `Pill`'s tone backgrounds are `/10` opacity vs. this
 * component's original `/15`, a trivial visual difference per that
 * ticket's resolution, not a functional gap.
 */
export function SavedStatusPill({ status }: { status: SaveStatus }) {
  const { t } = useTranslation();
  return (
    <Pill tone={TONE[status]} dot={false}>
      {t(LABEL_KEYS[status])}
    </Pill>
  );
}

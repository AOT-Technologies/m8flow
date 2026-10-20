import { Trans, useTranslation } from 'react-i18next';

import { literalTransValues } from '@/i18n';
import { Alert } from '@/components/library/alert/Alert';
import { Button } from '@/components/ui/button';

export type NotPrimaryBannerProps = {
  primaryFileName: string;
  /** Omitted for users who cannot manage the catalog — they still get told. */
  onSetPrimary?: () => void;
  submitting?: boolean;
};

/**
 * Warns that edits to this file do not change what the process runs (M8F-510).
 *
 * The "Saved" pill only ever means "no unsaved edits in this session", and the
 * toolbar's "Set as primary" button was the only hint that the open file was
 * not the one the process actually starts from — easy to read a successfully
 * uploaded, non-primary .bpmn as having silently failed to persist.
 */
export function NotPrimaryBanner({
  primaryFileName,
  onSetPrimary,
  submitting,
}: NotPrimaryBannerProps) {
  const { t } = useTranslation();
  return (
    <Alert tone="warning" className="w-fit max-w-full items-center px-3 py-1.5">
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span>
          <Trans
            {...literalTransValues}
            i18nKey="modeler.banner.notPrimary"
            values={{ fileName: primaryFileName }}
            components={{ code: <span className="font-mono" /> }}
          />
        </span>
        {onSetPrimary ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onSetPrimary}
            disabled={submitting}
            className="h-6 px-2"
          >
            {submitting ? t('modeler.banner.settingPrimary') : t('modeler.toolbar.setAsPrimary')}
          </Button>
        ) : null}
      </span>
    </Alert>
  );
}

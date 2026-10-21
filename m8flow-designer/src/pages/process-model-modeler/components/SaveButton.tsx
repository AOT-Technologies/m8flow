import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

export type SaveButtonProps = {
  onClick: () => void;
  disabled?: boolean;
};

/** Shown instead of SavedStatusPill whenever the diagram is dirty. */
export function SaveButton({ onClick, disabled }: SaveButtonProps) {
  const { t } = useTranslation();
  return (
    <Button type="button" variant="pill-info" size="pill" onClick={onClick} disabled={disabled}>
      {t('modeler.save')}
    </Button>
  );
}

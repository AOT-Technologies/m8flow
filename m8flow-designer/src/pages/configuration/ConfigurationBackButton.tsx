import { ChevronLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';

export function ConfigurationBackButton({
  label,
  to = '/configuration/secrets',
}: {
  label?: string;
  to?: string;
} = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="mb-1.5 rounded-full font-semibold"
      onClick={() => navigate(to)}
    >
      <ChevronLeft className="size-3.5" strokeWidth={2} aria-hidden />
      {label ?? t('configuration.title')}
    </Button>
  );
}

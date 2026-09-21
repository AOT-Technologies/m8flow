import { ChevronLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';

export function ConfigurationBackButton() {
  const navigate = useNavigate();

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="mb-1.5 rounded-full font-semibold"
      onClick={() => navigate('/configuration/secrets')}
    >
      <ChevronLeft className="size-3.5" strokeWidth={2} aria-hidden />
      Configuration
    </Button>
  );
}

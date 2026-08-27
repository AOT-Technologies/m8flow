import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import ProcessModelCard from './ProcessModelCard';
import {
  clearProcessTenantLabels,
  registerProcessTenantLabels,
} from './processTenantLabelRegistry';

vi.mock('../../services/UserService', () => ({
  default: { isSuperAdmin: vi.fn() },
}));

vi.mock('../../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@spiff-core/views/StartProcess/ProcessModelCard', () => ({
  default: ({ onStartProcess }: { onStartProcess?: () => void }) => (
    <div className="MuiCardActions-root">
      <button type="button" onClick={onStartProcess}>start_process</button>
    </div>
  ),
}));

import UserService from '../../services/UserService';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';

const theme = createTheme();

function renderCard(model: Record<string, unknown>, onStartProcess = vi.fn()) {
  render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <ProcessModelCard model={model as any} onStartProcess={onStartProcess} />
      </MemoryRouter>
    </ThemeProvider>,
  );
  return onStartProcess;
}

describe('ProcessModelCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearProcessTenantLabels();
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
  });

  it('renders a tenant chip only for super-admin users', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({ id: 'hr/onboarding', tenantName: 'Acme Co.' });
    expect(screen.getByTestId('process-model-tenant-chip-hr/onboarding')).toHaveTextContent('Acme Co.');
  });

  it('hides the tenant chip for non-super-admin users', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderCard({ id: 'hr/onboarding', tenantName: 'Acme Co.' });
    expect(screen.queryByTestId('process-model-tenant-chip-hr/onboarding')).toBeNull();
  });

  it('uses the registered tenant label for slim process-model responses', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    registerProcessTenantLabels([{ id: 'hr/onboarding', tenantName: 'Acme Co.' }]);
    renderCard({ id: 'hr/onboarding' });
    expect(screen.getByTestId('process-model-tenant-chip-hr/onboarding')).toHaveTextContent('Acme Co.');
  });

  it('prevents unscoped super-admin process starts', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
    const onStartProcess = renderCard({ id: 'hr/onboarding' });

    fireEvent.click(screen.getByRole('button', { name: 'start_process' }));
    expect(onStartProcess).not.toHaveBeenCalled();
  });
});

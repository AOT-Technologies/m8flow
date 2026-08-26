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
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

const navigate = vi.fn();

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigate,
}));

vi.mock('../../services/LocalStorageService', () => ({
  getStorageValue: vi.fn(() => '[]'),
}));

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: vi.fn(),
  },
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../../services/UserService';

const theme = createTheme();

function renderCard(model: Record<string, unknown>) {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <ProcessModelCard model={model as any} />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('ProcessModelCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearProcessTenantLabels();
  });

  it('renders tenant chip when user is super-admin and tenantName is present', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({
      id: 'hr/onboarding',
      display_name: 'Onboarding',
      description: 'Onboarding workflow',
      tenantId: 'tenant-a',
      tenantName: 'Acme Co.',
    });
    expect(screen.getByTestId('process-model-tenant-chip-hr/onboarding')).toHaveTextContent(
      'Acme Co.',
    );
  });

  it('hides tenant chip for non-super-admin even if tenantName is present', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderCard({
      id: 'hr/onboarding',
      display_name: 'Onboarding',
      description: '',
      tenantId: 'tenant-a',
      tenantName: 'Acme Co.',
    });
    expect(screen.queryByTestId('process-model-tenant-chip-hr/onboarding')).toBeNull();
  });

  it('hides tenant chip when tenantName is missing for super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({
      id: 'hr/onboarding',
      display_name: 'Onboarding',
      description: '',
    });
    expect(screen.queryByTestId('process-model-tenant-chip-hr/onboarding')).toBeNull();
  });

  it('falls back to the registered tenant label when the model props are slim', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    registerProcessTenantLabels([
      {
        id: 'hr/onboarding',
        tenantName: 'Acme Co.',
      },
    ]);
    renderCard({
      id: 'hr/onboarding',
      display_name: 'Onboarding',
      description: '',
    });
    expect(screen.getByTestId('process-model-tenant-chip-hr/onboarding')).toHaveTextContent(
      'Acme Co.',
    );
  });

  it('disables process start when the page requires a concrete tenant selection', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({
      id: 'hr/onboarding',
      display_name: 'Onboarding',
      description: '',
      tenantName: 'Acme Co.',
    } as any);

    const button = screen.getByRole('button', { name: 'start_process' });
    expect(button).toBeEnabled();

    fireEvent.click(button);
    expect(navigate).toHaveBeenCalledWith('/hr:onboarding/start');
  });
});

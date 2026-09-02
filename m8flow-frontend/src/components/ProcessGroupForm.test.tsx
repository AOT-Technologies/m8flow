import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import ProcessGroupForm from './ProcessGroupForm';

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(),
}));

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('@spiff-core/components/ProcessGroupForm', () => ({
  default: () => <button type="button">submit</button>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));

import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import UserService from '../services/UserService';

const theme = createTheme();

const baseGroup = {
  id: 'finance',
  display_name: 'Finance',
  description: '',
  messages: [],
};

function renderForm(mode = 'new') {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ThemeProvider theme={theme}>
      <MemoryRouter>{children}</MemoryRouter>
    </ThemeProvider>
  );
  return render(
    <ProcessGroupForm
      mode={mode}
      processGroup={baseGroup as any}
      setProcessGroup={vi.fn()}
    />,
    { wrapper },
  );
}

describe('ProcessGroupForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
  });

  it('requires a global tenant selection for super-admin create', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderForm('new');

    expect(screen.getByTestId('super-admin-tenant-alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'submit' })).toBeDisabled();
  });

  it('delegates to the core form when the super-admin has selected a tenant', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderForm('new');

    expect(screen.queryByTestId('super-admin-tenant-alert')).toBeNull();
    expect(screen.getByRole('button', { name: 'submit' })).not.toBeDisabled();
  });
});

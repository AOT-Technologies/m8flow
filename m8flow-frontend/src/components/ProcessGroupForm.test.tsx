import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock('../helpers', () => ({
  modifyProcessIdentifierForPathParam: (value: string) => value,
  slugifyString: (value: string) => value.toLowerCase().replace(/\s+/g, '-'),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import HttpService from '../services/HttpService';
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
    expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
  });

  it('submits a root process-group create when the super-admin has selected a tenant', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderForm('new');

    fireEvent.click(screen.getByRole('button', { name: 'submit' }));

    await waitFor(() => {
      expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
        expect.objectContaining({
          path: '/process-groups',
          httpMethod: 'POST',
          postBody: expect.objectContaining({
            id: 'finance',
            display_name: 'Finance',
          }),
        }),
      );
    });
  });
});

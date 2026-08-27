import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import CreateProcessModelFromTemplateModal from './CreateProcessModelFromTemplateModal';

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(),
}));

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../services/TemplateService', () => ({
  default: {
    createProcessModelFromTemplate: vi.fn(),
  },
}));

vi.mock('../hooks/useProcessGroups', () => ({
  default: vi.fn(() => ({
    processGroups: [
      {
        id: 'finance',
        display_name: 'Finance',
        process_groups: [],
        process_models: [],
      },
    ],
    loading: false,
  })),
}));

vi.mock('../utils/templateKey', () => ({
  nameToTemplateKey: () => 'approval-workflow',
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import UserService from '../services/UserService';

const theme = createTheme();

function renderModal() {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ThemeProvider theme={theme}>
      <MemoryRouter>{children}</MemoryRouter>
    </ThemeProvider>
  );

  return render(
    <CreateProcessModelFromTemplateModal
      open
      onClose={vi.fn()}
      template={{
        id: 5,
        name: 'Approval Workflow',
        description: 'Approval workflow template',
        isPublished: true,
        version: 'V1',
      } as any}
    />,
    { wrapper },
  );
}

describe('CreateProcessModelFromTemplateModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
  });

  it('blocks super-admin create-from-template when All Tenants is selected', () => {
    renderModal();

    expect(
      screen.getByTestId('create-from-template-tenant-alert'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('create-from-template-submit-button')).toBeDisabled();
    expect(
      within(screen.getByTestId('create-from-template-group-select')).getByRole('combobox'),
    ).toBeDisabled();
  });

  it('allows super-admin create-from-template after a tenant is selected', () => {
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });

    renderModal();

    expect(screen.queryByTestId('create-from-template-tenant-alert')).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId('create-from-template-group-select')).getByRole('combobox'),
    ).toBeEnabled();
  });
});

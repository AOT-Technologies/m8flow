import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type React from 'react';
import ProcessGroupCard from './ProcessGroupCard';

vi.mock('../../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../../services/UserService';

const theme = createTheme();

function renderCard(group: Record<string, unknown>) {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <ProcessGroupCard group={group as any} />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('ProcessGroupCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders tenant chip when user is super-admin and tenantName is present', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({
      id: 'hr',
      display_name: 'HR',
      description: 'HR processes',
      process_groups: [],
      process_models: [],
      tenantId: 'tenant-a',
      tenantName: 'Acme Co.',
    });
    expect(screen.getByTestId('process-group-tenant-chip-hr')).toHaveTextContent(
      'Acme Co.',
    );
  });

  it('hides tenant chip for non-super-admin even if tenantName is present', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderCard({
      id: 'hr',
      display_name: 'HR',
      description: '',
      process_groups: [],
      process_models: [],
      tenantId: 'tenant-a',
      tenantName: 'Acme Co.',
    });
    expect(screen.queryByTestId('process-group-tenant-chip-hr')).toBeNull();
  });

  it('hides tenant chip when tenantName is missing for super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({
      id: 'hr',
      display_name: 'HR',
      description: '',
      process_groups: [],
      process_models: [],
    });
    expect(screen.queryByTestId('process-group-tenant-chip-hr')).toBeNull();
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import ProcessModelCard from './ProcessModelCard';

vi.mock('../../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('@spiff-core/views/StartProcess/ProcessModelCard', () => ({
  default: () => <div data-testid="upstream-process-model-card" />,
}));

import UserService from '../../services/UserService';

const theme = createTheme();

function renderCard(model: Record<string, unknown>) {
  return render(
    <ThemeProvider theme={theme}>
      <ProcessModelCard model={model as { id: string }} />
    </ThemeProvider>,
  );
}

describe('ProcessModelCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders tenant chip when user is super-admin and tenantName is present', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({
      id: 'invoice',
      display_name: 'Invoice',
      tenantName: 'Acme Co.',
    });
    expect(
      screen.getByTestId('process-model-tenant-chip-invoice'),
    ).toHaveTextContent('Acme Co.');
  });

  it('hides tenant chip for non-super-admin even if tenantName is present', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderCard({
      id: 'invoice',
      display_name: 'Invoice',
      tenantName: 'Acme Co.',
    });
    expect(
      screen.queryByTestId('process-model-tenant-chip-invoice'),
    ).toBeNull();
  });

  it('hides tenant chip when tenantName is missing for super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderCard({
      id: 'invoice',
      display_name: 'Invoice',
    });
    expect(
      screen.queryByTestId('process-model-tenant-chip-invoice'),
    ).toBeNull();
  });
});

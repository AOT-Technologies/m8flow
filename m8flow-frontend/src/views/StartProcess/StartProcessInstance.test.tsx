import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import StartProcessInstance from './StartProcessInstance';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(),
}));

vi.mock('../../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('@spiff-core/views/StartProcess/StartProcessInstance', () => ({
  default: () => <div data-testid="upstream-start-process" />,
}));

import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import UserService from '../../services/UserService';

describe('StartProcessInstance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
  });

  it('shows a tenant-selection alert for super-admin under All Tenants', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    render(
      <MemoryRouter>
        <StartProcessInstance />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('start-process-tenant-alert')).toBeInTheDocument();
  });

  it('delegates process start to the upstream route when a tenant is selected', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });

    render(
      <MemoryRouter>
        <StartProcessInstance />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('upstream-start-process')).toBeInTheDocument();
  });
});

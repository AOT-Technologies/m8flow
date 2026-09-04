import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import StartProcessInstance from './StartProcessInstance';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  };
});

vi.mock('../../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(),
}));

vi.mock('../../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import UserService from '../../services/UserService';
import HttpService from '../../services/HttpService';

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

  it('starts after a super-admin selects a tenant without violating hook order', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    const { rerender } = render(
      <MemoryRouter>
        <StartProcessInstance />
      </MemoryRouter>,
    );

    expect(vi.mocked(HttpService.makeCallToBackend)).not.toHaveBeenCalled();

    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    rerender(
      <MemoryRouter>
        <StartProcessInstance />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(vi.mocked(HttpService.makeCallToBackend)).toHaveBeenCalledWith(
        expect.objectContaining({
          httpMethod: 'POST',
          path: '/v1.0/process-instances/',
          tenantId: 'tenant-a',
        }),
      );
    });
  });
});

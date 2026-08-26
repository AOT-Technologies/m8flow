import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import StartProcessInstance from './StartProcessInstance';

const navigate = vi.fn();
const addError = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => navigate,
    useParams: () => ({ modifiedProcessModelId: 'hr:onboarding' }),
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('../../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(),
}));

vi.mock('../../helpers', () => ({
  modifyProcessIdentifierForPathParam: (value: string) => value,
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

vi.mock('@spiffworkflow-frontend/hooks/UseApiError', () => ({
  default: () => ({
    addError,
  }),
}));

import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import HttpService from '../../services/HttpService';
import UserService from '../../services/UserService';

describe('StartProcessInstance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
  });

  it('shows a tenant-selection alert and skips the start call for super-admin under All Tenants', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    render(
      <MemoryRouter>
        <StartProcessInstance />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('start-process-tenant-alert')).toBeInTheDocument();
    expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
  });

  it('starts the process when a concrete tenant is selected', async () => {
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

    await waitFor(() => {
      expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
        expect.objectContaining({
          path: '/v1.0/process-instances/hr:onboarding',
          httpMethod: 'POST',
        }),
      );
    });
  });
});

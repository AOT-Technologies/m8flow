import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Homepage from './Homepage';

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(() => ({
    selectedTenantId: '',
    setSelectedTenantId: vi.fn(),
  })),
}));

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock('../components/TaskTable', () => ({
  default: () => null,
}));

vi.mock('../components/HeaderTabs', () => ({
  default: () => null,
}));

vi.mock('../components/TaskControls', () => ({
  default: () => null,
}));

vi.mock('./OnboardingView', () => ({
  default: () => null,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import HttpService from '../services/HttpService';

function renderHome() {
  return render(
    <MemoryRouter>
      <Homepage viewMode="table" setViewMode={() => {}} isMobile={false} />
    </MemoryRouter>,
  );
}

describe('Homepage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('fetches /tasks?tenantId= for super-admin with a selected tenant', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderHome();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({ path: '/tasks?tenantId=tenant-a' }),
    );
  });

  it('fetches /tasks without tenantId for non-super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderHome();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({ path: '/tasks' }),
    );
  });

  it('fetches /tasks without tenantId when super-admin has no selected tenant', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
    renderHome();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({ path: '/tasks' }),
    );
  });
});

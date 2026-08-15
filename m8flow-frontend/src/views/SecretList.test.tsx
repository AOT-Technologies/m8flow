import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import SecretList from './SecretList';

const h = vi.hoisted(() => ({
  ability: { can: () => true },
  targetUris: {
    authenticationListPath: '/authentications',
    secretListPath: '/secrets',
  },
}));

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

vi.mock('../hooks/PermissionService', () => ({
  usePermissionFetcher: () => ({
    ability: h.ability,
    permissionsLoaded: true,
  }),
}));

vi.mock('../hooks/UriListForPermissions', () => ({
  useUriListForPermissions: () => ({
    targetUris: h.targetUris,
  }),
}));

vi.mock('../helpers', () => ({
  getPageInfoFromSearchParams: () => ({ page: 1, perPage: 10 }),
}));

vi.mock('../components/PaginationForTable', () => ({
  default: ({ tableToDisplay }: { tableToDisplay: React.ReactNode }) => (
    <div data-testid="pagination-mock">{tableToDisplay}</div>
  ),
}));

vi.mock('@casl/react', () => ({
  Can: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock('react-icons/md', () => ({
  MdDelete: () => <span data-testid="delete-icon" />,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import HttpService from '../services/HttpService';

function stubSecretsList() {
  vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts: any) => {
    opts.successCallback({
      results: [
        {
          id: 1,
          key: 'api-key',
          username: 'editor',
          tenantName: 'Acme',
          tenantId: 'tenant-a',
        },
      ],
      pagination: { total: 1, pages: 1 },
    });
  });
}

function renderList() {
  return render(
    <MemoryRouter>
      <SecretList />
    </MemoryRouter>,
  );
}

describe('SecretList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stubSecretsList();
  });

  it('sends tenantId and shows the tenant column for super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderList();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/secrets?per_page=10&page=1&tenantId=tenant-a',
      }),
    );
    expect(screen.getByTestId('secret-list-tenant-cell')).toHaveTextContent(
      'Acme',
    );
  });

  it('omits tenantId and the tenant column for non-super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderList();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/secrets?per_page=10&page=1',
      }),
    );
    expect(screen.queryByTestId('secret-list-tenant-cell')).toBeNull();
  });

  it('shows an inline vault-down error when the secrets list request fails', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts: any) => {
      opts.failureCallback?.({ message: 'Vault is down.' });
    });

    renderList();

    expect(await screen.findByTestId('secret-list-error')).toHaveTextContent(
      'Vault is down.',
    );
  });
});

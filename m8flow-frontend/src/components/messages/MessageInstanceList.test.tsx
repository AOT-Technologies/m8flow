import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import MessageInstanceList from './MessageInstanceList';

vi.mock('../../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(() => ({
    selectedTenantId: '',
    setSelectedTenantId: vi.fn(),
  })),
}));

vi.mock('../../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock('../../helpers', () => ({
  getPageInfoFromSearchParams: () => ({ page: 1, perPage: 10 }),
  modifyProcessIdentifierForPathParam: (value: string) => value,
}));

vi.mock('../PaginationForTable', () => ({
  default: ({ tableToDisplay }: { tableToDisplay: React.ReactNode }) => (
    <div data-testid="pagination-mock">{tableToDisplay}</div>
  ),
}));

vi.mock('../ProcessBreadcrumb', () => ({
  default: () => null,
}));

vi.mock('./messageListColumns', () => ({
  buildMessageColumns: () => [],
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../../services/UserService';
import { useGlobalTenant } from '../../contexts/GlobalTenantContext';
import HttpService from '../../services/HttpService';

function stubMessages() {
  vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts: any) => {
    opts.successCallback({
      results: [],
      pagination: { total: 0, pages: 0 },
    });
  });
}

function renderList() {
  return render(
    <MemoryRouter>
      <MessageInstanceList />
    </MemoryRouter>,
  );
}

describe('MessageInstanceList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stubMessages();
  });

  it('appends tenantId for super-admin with a selected tenant', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderList();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/messages?per_page=10&page=1&tenantId=tenant-a',
      }),
    );
  });

  it('omits tenantId for non-super-admin even when a tenant is selected', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderList();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/messages?per_page=10&page=1',
      }),
    );
  });
});

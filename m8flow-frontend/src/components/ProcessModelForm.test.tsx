import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import ProcessModelForm from './ProcessModelForm';

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(),
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

import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';
import HttpService from '../services/HttpService';

const theme = createTheme();

const baseModel = {
  id: 'my-model',
  display_name: 'My Model',
  description: '',
  metadata_extraction_paths: [],
  fault_or_suspend_on_exception: false,
  exception_notification_addresses: [],
};

function renderForm(mode = 'new') {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ThemeProvider theme={theme}>
      <MemoryRouter>{children}</MemoryRouter>
    </ThemeProvider>
  );
  return render(
    <ProcessModelForm
      mode={mode}
      processModel={baseModel as any}
      processGroupId="finance"
      setProcessModel={vi.fn()}
    />,
    { wrapper },
  );
}

describe('ProcessModelForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: '',
      setSelectedTenantId: vi.fn(),
    });
  });

  it('requires a global tenant selection for super-admin create', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderForm('new');

    expect(
      await screen.findByTestId('super-admin-tenant-alert'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('process-model-submit-button')).toBeDisabled();
    expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
  });

  it('submits a super-admin create when the global tenant selector is concrete', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    renderForm('new');

    fireEvent.click(screen.getByTestId('process-model-submit-button'));

    await waitFor(() => {
      expect(HttpService.makeCallToBackend).toHaveBeenCalledTimes(1);
    });
    const call = vi.mocked(HttpService.makeCallToBackend).mock.calls[0][0];
    expect(call.httpMethod).toBe('POST');
    expect(call.path).toBe('/process-models/finance');
    expect(call.postBody).toEqual(
      expect.objectContaining({
        id: 'finance/my-model',
        display_name: 'My Model',
      }),
    );
    expect(call.postBody).not.toHaveProperty('m8f_tenant_id');
  });

  it('does not require tenant selection for non-super-admin create', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderForm('new');

    expect(screen.queryByTestId('super-admin-tenant-alert')).toBeNull();
    fireEvent.click(screen.getByTestId('process-model-submit-button'));

    await waitFor(() => {
      expect(HttpService.makeCallToBackend).toHaveBeenCalledTimes(1);
    });
    const call = vi.mocked(HttpService.makeCallToBackend).mock.calls[0][0];
    expect(call.postBody).not.toHaveProperty('m8f_tenant_id');
  });
});

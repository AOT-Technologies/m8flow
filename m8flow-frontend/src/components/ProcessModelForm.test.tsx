import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import ProcessModelForm from './ProcessModelForm';

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../services/TenantService', () => ({
  default: {
    getAllTenants: vi.fn(),
  },
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
import TenantService from '../services/TenantService';
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
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>
        <MemoryRouter>{children}</MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>
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
    vi.mocked(TenantService.getAllTenants).mockResolvedValue([
      { id: 'tenant-a', name: 'Acme', slug: 'acme' } as any,
    ]);
  });

  it('requires a tenant on super-admin create and includes m8f_tenant_id in the POST body', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    renderForm('new');

    expect(
      await screen.findByTestId('super-admin-tenant-select'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('process-model-submit-button'));
    expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
    expect(
      await screen.findByText('tenant_required_for_super_admin'),
    ).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /Acme \(acme\)/ }));

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
        m8f_tenant_id: 'tenant-a',
      }),
    );
  });

  it('does not show a tenant select or send m8f_tenant_id for non-super-admin create', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    renderForm('new');

    expect(screen.queryByTestId('super-admin-tenant-select')).toBeNull();
    fireEvent.click(screen.getByTestId('process-model-submit-button'));

    await waitFor(() => {
      expect(HttpService.makeCallToBackend).toHaveBeenCalledTimes(1);
    });
    const call = vi.mocked(HttpService.makeCallToBackend).mock.calls[0][0];
    expect(call.postBody).not.toHaveProperty('m8f_tenant_id');
    expect(TenantService.getAllTenants).not.toHaveBeenCalled();
  });
});

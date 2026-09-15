import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import { activeTenantFromContext, capabilitiesFromContext } from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => ({
    tenants: [],
    refreshTenants: () => {},
    organizationMemberships: [],
    activeTenantLabel: null,
  }),
}));
import ProcessInstancesPage from './ProcessInstancesPage';

function renderWithOutlet(context: SessionFixtureContext, initial = '/process-instances') {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/process-instances" element={<ProcessInstancesPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function mockInstance(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 42,
    process_model_identifier: 'finance/invoice-approval',
    process_model_display_name: 'Invoice Approval',
    status: 'complete',
    started_by: 'editor',
    start_in_seconds: 1_700_000_000,
    end_in_seconds: 1_700_000_060,
    ...overrides,
  };
}

/** The page fires two independent requests (instance list + owner options).
 * Route the mock by URL so each gets the right shape, and expose helpers to
 * inspect only the list calls (owners calls would otherwise pollute counts). */
function stubFetch({
  results = [] as ReturnType<typeof mockInstance>[],
  pagination = { count: 0, total: 0, pages: 0 },
  owners = [] as string[],
} = {}) {
  const fetchMock = vi.fn().mockImplementation((input: unknown) => {
    const url = String(input);
    const body = url.includes('/process-instances/owners') ? { owners } : { results, pagination };
    return Promise.resolve({ ok: true, json: async () => body });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function listCalls(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls.filter((c) => !String(c[0]).includes('/process-instances/owners'));
}
function lastListUrl(fetchMock: ReturnType<typeof vi.fn>) {
  const calls = listCalls(fetchMock);
  return String(calls[calls.length - 1]?.[0]);
}

describe('ProcessInstancesPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('prompts super-admin when All Tenants is selected', () => {
    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: true });
    expect(screen.getByText('Choose a tenant')).toBeInTheDocument();
  });

  it('fetches and renders instances for a concrete tenant', async () => {
    const fetchMock = stubFetch({ results: [mockInstance()], pagination: { count: 1, total: 1, pages: 1 } });

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => {
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
    });
    const url = lastListUrl(fetchMock);
    expect(url).toContain('/v1.0/m8flow/process-instances');
    expect(url).toContain('tenantId=t1');
    // "Complete" is the instance row's own status Pill — the Status filter
    // (a SortDropdown, ticket 06) doesn't render its option list into the
    // DOM until opened, unlike a native <select>'s always-present <option>s.
    expect(screen.getAllByText('Complete').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1 instance').length).toBeGreaterThan(0);
  });

  it('requests the owner options and renders them in the filter', async () => {
    const user = userEvent.setup();
    stubFetch({ results: [mockInstance()], pagination: { count: 1, total: 1, pages: 1 }, owners: ['amir', 'zoe'] });

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /Started by/ }));
    expect(await screen.findByRole('menuitem', { name: 'amir' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'zoe' })).toBeInTheDocument();
  });

  it('applies the started_by filter as a server-side param', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch({ owners: ['amir', 'zoe'] });

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });
    await waitFor(() => expect(listCalls(fetchMock).length).toBe(1));

    await user.click(screen.getByRole('button', { name: /Started by/ }));
    await user.click(await screen.findByRole('menuitem', { name: 'amir' }));

    await waitFor(() => expect(lastListUrl(fetchMock)).toContain('started_by=amir'));
  });

  it('applies the sort control as a server-side param', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch();

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });
    await waitFor(() => expect(listCalls(fetchMock).length).toBe(1));

    await user.click(screen.getByRole('button', { name: /^Sort:/ }));
    await user.click(await screen.findByRole('menuitem', { name: 'Oldest' }));

    await waitFor(() => expect(lastListUrl(fetchMock)).toContain('sort=oldest'));
  });

  it('applies the rows-per-page selector as a server-side per_page param', async () => {
    const fetchMock = stubFetch({ results: [mockInstance()], pagination: { count: 1, total: 1, pages: 1 } });

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Rows per page'), { target: { value: '50' } });

    await waitFor(() => expect(lastListUrl(fetchMock)).toContain('per_page=50'));
  });

  it('shows a "1–N of total" range in the footer', async () => {
    stubFetch({ results: [mockInstance()], pagination: { count: 1, total: 1, pages: 1 } });

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => expect(screen.getByText('1–1 of 1')).toBeInTheDocument());
  });

  it('debounces the search box into a server-side search param', async () => {
    const fetchMock = stubFetch();

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => expect(listCalls(fetchMock).length).toBe(1));

    fireEvent.change(screen.getByLabelText('Search process instances'), {
      target: { value: 'invoice' },
    });

    await waitFor(() => expect(lastListUrl(fetchMock)).toContain('search=invoice'), { timeout: 1000 });
  });

  it('applies the status filter as a server-side param and resets to page 1', async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch();

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });
    await waitFor(() => expect(listCalls(fetchMock).length).toBe(1));

    await user.click(screen.getByRole('button', { name: /^Status:/ }));
    await user.click(await screen.findByRole('menuitem', { name: 'Error' }));

    await waitFor(() => expect(lastListUrl(fetchMock)).toContain('status=error'));
  });

  it('seeds the search box from a ?search= deep link (capstone ticket)', async () => {
    const fetchMock = stubFetch();

    renderWithOutlet(
      { scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true },
      '/process-instances?search=Invoice%20Approval',
    );

    expect(screen.getByLabelText('Search process instances')).toHaveValue('Invoice Approval');
    await waitFor(() => expect(lastListUrl(fetchMock)).toContain('search=Invoice+Approval'));
  });

  it('navigates to the instance detail route when a row is opened', async () => {
    stubFetch({ results: [mockInstance()], pagination: { count: 1, total: 1, pages: 1 } });

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Invoice Approval/ }));
  });

  it('exposes a read-only actions menu that copies the instance id', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText }, userAgent: 'test' });
    stubFetch({ results: [mockInstance()], pagination: { count: 1, total: 1, pages: 1 } });

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Instance actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Copy instance ID' }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith('42'));
  });
});

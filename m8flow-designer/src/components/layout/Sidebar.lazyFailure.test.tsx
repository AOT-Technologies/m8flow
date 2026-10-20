import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Sidebar } from './Sidebar';

// The picker's chunk fails to load (offline, or replaced by a deploy). Its own file, since
// vi.mock applies to every test in a file.
vi.mock('./SuperAdminTenantSelect', () => {
  throw new Error('Failed to fetch dynamically imported module');
});

const TENANTS = [{ id: 't1', name: 'Tenant One' }];

describe('Sidebar lazy tenant picker', () => {
  // The read-only box shows what the select would have: the selected tenant, or "All tenants".
  it.each([
    { selectedTenantId: 't1', shown: 'Tenant One' },
    { selectedTenantId: null, shown: 'All tenants' },
  ])('keeps the read-only box ($shown) when the picker fails to load', async ({ selectedTenantId, shown }) => {
    render(
      <MemoryRouter>
        <Sidebar showTenantSelector tenants={TENANTS} selectedTenantId={selectedTenantId} />
      </MemoryRouter>,
    );

    // Let the failed import reject and React re-render before looking.
    await act(() => vi.dynamicImportSettled());

    // The app is still rendered (the error did not escape), with no interactive select.
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.getByText(shown)).toBeInTheDocument();
  });
});

import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { Sidebar } from './Sidebar';

// The picker's chunk fails to load (offline, or replaced by a deploy). Its own file, since
// vi.mock applies to every test in a file.
vi.mock('./SuperAdminTenantSelect', () => {
  throw new Error('Failed to fetch dynamically imported module');
});

describe('Sidebar lazy tenant picker', () => {
  it('keeps the read-only tenant box when the picker fails to load', async () => {
    render(
      <MemoryRouter>
        <Sidebar showTenantSelector tenants={[{ id: 't1', name: 'Tenant One' }]} selectedTenantId="t1" />
      </MemoryRouter>,
    );

    // Let the failed import reject and React re-render before looking.
    await act(() => vi.dynamicImportSettled());

    expect(screen.getByText('Tenant One')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});

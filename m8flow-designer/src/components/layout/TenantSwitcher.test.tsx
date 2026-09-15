import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { finalizeTenantLogin } from '@/lib/auth';
import { TenantSwitcher } from './TenantSwitcher';

// The switch now reuses the tenant-select gate's finalization hop
// (finalizeTenantLogin -> a full-page navigation), not a hidden iframe.
// Mock just that navigation; keep getSelectedTenantId real (it reads the cookie).
vi.mock('@/lib/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/auth')>()),
  finalizeTenantLogin: vi.fn(),
}));

const finalize = vi.mocked(finalizeTenantLogin);

// Radix's DropdownMenu doesn't open under plain fireEvent.click in jsdom —
// use @testing-library/user-event throughout, per the map's Notes.
const ORGS = [
  { alias: 'org-a', id: 'org-a', name: 'Org A' },
  { alias: 'org-b', id: 'org-b', name: 'Org B' },
];

describe('TenantSwitcher', () => {
  beforeEach(() => {
    document.cookie = 'm8flow_selected_tenant=org-a; Path=/';
  });

  afterEach(() => {
    document.cookie = 'm8flow_selected_tenant=; Max-Age=0; Path=/';
    vi.restoreAllMocks();
    finalize.mockReset();
  });

  it('lists org memberships with the active one checked', async () => {
    const user = userEvent.setup();
    render(<TenantSwitcher activeTenantLabel="Org A" organizations={ORGS} />);

    await user.click(screen.getByTestId('nav-tenant-name'));
    expect(await screen.findByTestId('nav-tenant-option-org-a')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByTestId('nav-tenant-option-org-b')).not.toHaveAttribute('aria-disabled');
  });

  it('clicking the active org is a no-op — no navigation', async () => {
    const user = userEvent.setup();
    render(<TenantSwitcher activeTenantLabel="Org A" organizations={ORGS} />);

    await user.click(screen.getByTestId('nav-tenant-name'));
    await user.click(await screen.findByTestId('nav-tenant-option-org-a'));

    expect(finalize).not.toHaveBeenCalled();
  });

  it('selecting a different org finalizes onto it via the backend hop', async () => {
    const user = userEvent.setup();
    render(<TenantSwitcher activeTenantLabel="Org A" organizations={ORGS} />);

    await user.click(screen.getByTestId('nav-tenant-name'));
    await user.click(await screen.findByTestId('nav-tenant-option-org-b'));

    expect(finalize).toHaveBeenCalledTimes(1);
    expect(finalize).toHaveBeenCalledWith(ORGS[1]);
    // Trigger flips to the pending state so the click registers before the
    // page navigates away.
    expect(screen.getByTestId('nav-tenant-name')).toBeDisabled();
  });

  it('never touches localStorage during a switch', async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    render(<TenantSwitcher activeTenantLabel="Org A" organizations={ORGS} />);

    await user.click(screen.getByTestId('nav-tenant-name'));
    await user.click(await screen.findByTestId('nav-tenant-option-org-b'));

    expect(setItem).not.toHaveBeenCalled();
  });
});

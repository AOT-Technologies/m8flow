import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import {
  activeTenantFromContext,
  capabilitiesFromContext,
  tenantRegistryFromContext,
} from '@/components/session/testSupport';
import TenantManagementPage from './TenantManagementPage';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
const mockUseTenantRegistry = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => mockUseTenantRegistry(),
}));

const mockFetchTenantMembers = vi.fn();
const mockFetchAvailableTenantUsers = vi.fn();
const mockAddTenantMember = vi.fn();
const mockRemoveTenantMember = vi.fn();
const mockFetchTenantGroups = vi.fn();
const mockAddTenantGroupMember = vi.fn();
const mockRemoveTenantGroupMember = vi.fn();
const mockCreateTenantGroup = vi.fn();
const mockRenameTenantGroup = vi.fn();
const mockDeleteTenantGroup = vi.fn();
const mockGrantTenantGroupRole = vi.fn();
const mockRevokeTenantGroupRole = vi.fn();
const mockFetchTenantInvitations = vi.fn();
const mockCreateTenantInvitation = vi.fn();
const mockResendTenantInvitation = vi.fn();
const mockRevokeTenantInvitation = vi.fn();
const mockUpdateTenantName = vi.fn();
const mockRefreshTenants = vi.fn();
const mockGetSelectedTenantId = vi.fn((): string | null => 't1');
const mockGetActiveTenantDisplayLabel = vi.fn((): string | null => 'Acme Corp');

vi.mock('@/lib/auth', () => ({
  getSelectedTenantId: () => mockGetSelectedTenantId(),
  getActiveTenantDisplayLabel: () => mockGetActiveTenantDisplayLabel(),
}));

vi.mock('@/lib/tenantAdminApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/tenantAdminApi')>(
    '@/lib/tenantAdminApi',
  );
  return {
    ...actual,
    fetchTenantMembers: (...args: unknown[]) => mockFetchTenantMembers(...args),
    fetchAvailableTenantUsers: (...args: unknown[]) => mockFetchAvailableTenantUsers(...args),
    addTenantMember: (...args: unknown[]) => mockAddTenantMember(...args),
    removeTenantMember: (...args: unknown[]) => mockRemoveTenantMember(...args),
    fetchTenantGroups: (...args: unknown[]) => mockFetchTenantGroups(...args),
    addTenantGroupMember: (...args: unknown[]) => mockAddTenantGroupMember(...args),
    removeTenantGroupMember: (...args: unknown[]) => mockRemoveTenantGroupMember(...args),
    createTenantGroup: (...args: unknown[]) => mockCreateTenantGroup(...args),
    renameTenantGroup: (...args: unknown[]) => mockRenameTenantGroup(...args),
    deleteTenantGroup: (...args: unknown[]) => mockDeleteTenantGroup(...args),
    grantTenantGroupRole: (...args: unknown[]) => mockGrantTenantGroupRole(...args),
    revokeTenantGroupRole: (...args: unknown[]) => mockRevokeTenantGroupRole(...args),
  };
});

vi.mock('@/lib/tenantsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/tenantsApi')>('@/lib/tenantsApi');
  return {
    ...actual,
    updateTenantName: (...args: unknown[]) => mockUpdateTenantName(...args),
  };
});

vi.mock('@/lib/invitationManagementApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/invitationManagementApi')>(
    '@/lib/invitationManagementApi',
  );
  return {
    ...actual,
    fetchTenantInvitations: (...args: unknown[]) => mockFetchTenantInvitations(...args),
    createTenantInvitation: (...args: unknown[]) => mockCreateTenantInvitation(...args),
    resendTenantInvitation: (...args: unknown[]) => mockResendTenantInvitation(...args),
    revokeTenantInvitation: (...args: unknown[]) => mockRevokeTenantInvitation(...args),
  };
});

function renderWithOutlet(
  context: Partial<SessionFixtureContext> = {},
  path = '/tenant-management',
) {
  const full: SessionFixtureContext = {
    scopedTenantId: null,
    selectedTenantId: null,
    isSuperAdmin: false,
    canManageTenant: true,
    refreshTenants: mockRefreshTenants,
    ...context,
  };
  mockUseActiveTenant.mockReturnValue({
    ...activeTenantFromContext(full),
    // TenantManagement reads the cookie-authoritative active tenant, which the
    // suite supplies via the getSelectedTenantId mock — not scopedTenantId.
    activeTenantId: mockGetSelectedTenantId(),
  });
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(full));
  mockUseTenantRegistry.mockReturnValue(tenantRegistryFromContext(full));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={full} />}>
          <Route path="/tenants" element={<div data-testid="tenants-registry">tenants-list</div>} />
          <Route path="/tenant-management" element={<TenantManagementPage />} />
          <Route path="/tenant-management/:tenantId" element={<TenantManagementPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const EDITOR = {
  id: 'u1',
  username: 'editor',
  email: 'editor@example.com',
  display_name: 'Ed Itor',
  roles: ['editor'] as const,
  groups: [{ id: 'g1', name: 'editors' }],
};

const GROUPS = {
  tenant_id: 't1',
  search: '',
  offset: 0,
  limit: 100,
  has_more: false,
  groups: [
    {
      id: 'g1',
      name: 'editors',
      path: '/editors',
      mapped_roles: ['editor'],
      member_count: 1,
      members: [],
    },
    {
      id: 'g2',
      name: 'reviewers',
      path: '/reviewers',
      mapped_roles: ['reviewer'],
      member_count: 0,
      members: [],
    },
  ],
};

describe('TenantManagementPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mockGetSelectedTenantId.mockReturnValue('t1');
    mockGetActiveTenantDisplayLabel.mockReturnValue('Acme Corp');
    mockFetchTenantMembers.mockResolvedValue({
      tenant_id: 't1',
      search: '',
      offset: 0,
      limit: 10,
      has_more: false,
      members: [EDITOR],
    });
    mockFetchTenantGroups.mockResolvedValue(GROUPS);
    mockFetchTenantInvitations.mockResolvedValue({
      tenant_id: 't1',
      results: [],
      total: 0,
      offset: 0,
      limit: 100,
    });
    mockFetchAvailableTenantUsers.mockResolvedValue({
      tenant_id: 't1',
      search: '',
      offset: 0,
      limit: 10,
      has_more: false,
      users: [{ id: 'u2', username: 'reviewer', email: 'r@example.com', display_name: 'Rev' }],
    });
  });

  it('explains denial and does not fetch when the role cannot manage the tenant', () => {
    renderWithOutlet({ canManageTenant: false });
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(mockFetchTenantMembers).not.toHaveBeenCalled();
    expect(screen.queryByTestId('tenant-member-add-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('tenant-invite-user-button')).not.toBeInTheDocument();
  });

  it('redirects super-admin from /tenant-management to the tenants registry', () => {
    renderWithOutlet({
      isSuperAdmin: true,
      scopedTenantId: null,
      selectedTenantId: null,
      canManageTenant: true,
    });
    expect(screen.getByTestId('tenants-registry')).toBeInTheDocument();
    expect(mockFetchTenantMembers).not.toHaveBeenCalled();
  });

  it('lists members for a tenant-admin using the active-tenant cookie', async () => {
    renderWithOutlet({ canManageTenant: true, isSuperAdmin: false });

    expect(await screen.findByText('Ed Itor')).toBeInTheDocument();
    expect(screen.getAllByText('editor').length).toBeGreaterThan(0);
    expect(screen.getByTestId('tenant-member-role-chip-editor-editor')).toBeInTheDocument();
    expect(screen.getByTestId('tenant-member-group-chip-editor-editors')).toBeInTheDocument();
    expect(mockFetchTenantMembers).toHaveBeenCalledWith('t1', {
      search: '',
      offset: 0,
      limit: 10,
    });
    expect(screen.queryByTestId('tenant-invite-user-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pending-invitations-panel')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Tenants' })).not.toBeInTheDocument();
    expect(mockFetchTenantInvitations).not.toHaveBeenCalled();

    // Groups lives on its own tab (Users is the default) — the Groups tab's
    // own count badge reads from the same fetch, so it's already right
    // without switching.
    expect(screen.getByRole('tab', { name: /Groups/ })).toHaveTextContent('2');
    fireEvent.mouseDown(screen.getByRole('tab', { name: /Groups/ }));
    // The Groups panel is a fresh mount on tab switch (see TenantAdminPanel's
    // own comment on why Groups/Users unmount-on-switch is fine but
    // Invitations isn't) — its own fetch resolves async, so its table rows
    // need awaiting even though the toolbar's "Add Group" button (rendered
    // unconditionally, not gated on the fetch) doesn't.
    expect(screen.getByTestId('tenant-group-add-button')).toBeInTheDocument();
    expect(await screen.findByTestId('tenant-group-name-cell-g1')).toBeInTheDocument();
    expect(screen.getByTestId('tenant-group-role-chip-g1-editor')).toBeInTheDocument();
  });

  it('lists members for a super-admin against the tenant in the URL', async () => {
    mockGetSelectedTenantId.mockReturnValue(null);
    renderWithOutlet(
      {
        canManageTenant: true,
        isSuperAdmin: true,
        scopedTenantId: null,
        selectedTenantId: null,
        tenants: [{ id: 't9', name: 'Tenant Nine' }],
      },
      '/tenant-management/t9',
    );

    expect(await screen.findByText('Ed Itor')).toBeInTheDocument();
    expect(mockFetchTenantMembers).toHaveBeenCalledWith('t9', expect.any(Object));
    expect(screen.getByTestId('tenant-invite-user-button')).toBeInTheDocument();
    expect(screen.getByTestId('pending-invitations-panel')).toBeInTheDocument();
    expect(mockFetchTenantInvitations).toHaveBeenCalledWith('t9', { limit: 100 });
    expect(screen.getByRole('link', { name: 'Tenants' })).toHaveAttribute('href', '/tenants');
    expect(screen.getAllByText('Tenant Nine').length).toBeGreaterThan(0);
  });

  it('debounces the search box into a server-side search param', async () => {
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.change(screen.getByTestId('tenant-member-search-input'), {
      target: { value: 'ed' },
    });

    await waitFor(
      () => {
        expect(mockFetchTenantMembers).toHaveBeenCalledWith(
          't1',
          expect.objectContaining({ search: 'ed', offset: 0, limit: 10 }),
        );
      },
      { timeout: 1000 },
    );
  });

  it('pages members with offset', async () => {
    mockFetchTenantMembers
      .mockResolvedValueOnce({
        tenant_id: 't1',
        search: '',
        offset: 0,
        limit: 10,
        has_more: true,
        members: [EDITOR],
      })
      .mockResolvedValueOnce({
        tenant_id: 't1',
        search: '',
        offset: 10,
        limit: 10,
        has_more: false,
        members: [{ ...EDITOR, username: 'viewer', display_name: 'Vi Ewer' }],
      });

    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    // Two "Next page" buttons exist on this page (members' pager and the
    // nested TenantGroupsSection's own pager) — the members one renders
    // first in DOM order.
    fireEvent.click(screen.getAllByRole('button', { name: 'Next page' })[0]);
    expect(await screen.findByText('viewer')).toBeInTheDocument();
    expect(mockFetchTenantMembers).toHaveBeenLastCalledWith(
      't1',
      expect.objectContaining({ offset: 10, limit: 10 }),
    );
  });

  it('adds an existing user with optional groups', async () => {
    mockAddTenantMember.mockResolvedValue({
      tenant_id: 't1',
      group_names: ['editors'],
      member: EDITOR,
    });
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.click(screen.getByTestId('tenant-member-add-button'));
    fireEvent.click(await screen.findByText('Rev'));
    fireEvent.click(screen.getByTestId('tenant-member-add-next'));
    fireEvent.click(await screen.findByTestId('tenant-add-member-group-editors'));
    fireEvent.click(screen.getByTestId('tenant-member-add-submit'));

    await waitFor(() => {
      expect(mockAddTenantMember).toHaveBeenCalledWith('t1', {
        username: 'reviewer',
        group_names: ['editors'],
      });
    });
  });

  it('keeps Next disabled on step 1 of the Add Member wizard until a user is picked', async () => {
    // Regression coverage for the map's own "Not yet specified" gap this
    // wizard closed: WizardModal's Continue button must stay disabled (not
    // silently advance, and never reach the add-member API) until step 1's
    // own selection state says otherwise.
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.click(screen.getByTestId('tenant-member-add-button'));
    expect(await screen.findByTestId('tenant-member-add-next')).toBeDisabled();

    fireEvent.click(await screen.findByText('Rev'));
    expect(screen.getByTestId('tenant-member-add-next')).toBeEnabled();
    expect(mockAddTenantMember).not.toHaveBeenCalled();
  });

  it('removes a member after confirm', async () => {
    mockRemoveTenantMember.mockResolvedValue(undefined);
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.click(screen.getByTestId('tenant-member-remove-button-editor'));
    expect(await screen.findByRole('heading', { name: 'Remove member' })).toBeInTheDocument();
    const removeButtons = screen.getAllByRole('button', { name: 'Remove' });
    fireEvent.click(removeButtons[removeButtons.length - 1]);

    await waitFor(() => {
      expect(mockRemoveTenantMember).toHaveBeenCalledWith('t1', 'editor');
    });
  });

  it('assigns and removes a member’s groups', async () => {
    mockAddTenantGroupMember.mockResolvedValue({});
    mockRemoveTenantGroupMember.mockResolvedValue({});
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.click(screen.getByTestId('tenant-member-manage-groups-button-editor'));
    fireEvent.click(await screen.findByTestId('tenant-member-group-toggle-reviewers'));
    fireEvent.click(screen.getByTestId('tenant-member-group-toggle-editors'));
    fireEvent.click(screen.getByTestId('tenant-member-groups-save'));

    await waitFor(() => {
      expect(mockAddTenantGroupMember).toHaveBeenCalledWith('t1', 'reviewers', 'editor');
      expect(mockRemoveTenantGroupMember).toHaveBeenCalledWith('t1', 'editors', 'editor');
    });
  });

  it('creates a group after normalizing the name', async () => {
    mockCreateTenantGroup.mockResolvedValue({
      tenant_id: 't1',
      group: {
        id: 'g3',
        name: 'QA Reviewers',
        mapped_roles: [],
        member_count: 0,
        members: [],
      },
    });
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.mouseDown(screen.getByRole('tab', { name: /Groups/ }));
    fireEvent.click(screen.getByTestId('tenant-group-add-button'));
    fireEvent.change(screen.getByTestId('tenant-group-name-input'), {
      target: { value: '  QA   Reviewers  ' },
    });
    fireEvent.click(screen.getByTestId('tenant-group-submit-button'));

    await waitFor(() => {
      expect(mockCreateTenantGroup).toHaveBeenCalledWith('t1', 'QA Reviewers');
    });
  });

  it('renames a group', async () => {
    mockRenameTenantGroup.mockResolvedValue({
      tenant_id: 't1',
      previous_group_name: 'reviewers',
      group: { ...GROUPS.groups[1], name: 'QA Reviewers' },
    });
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.mouseDown(screen.getByRole('tab', { name: /Groups/ }));
    fireEvent.click(await screen.findByTestId('tenant-group-rename-button-reviewers'));
    fireEvent.change(screen.getByTestId('tenant-group-rename-input'), {
      target: { value: 'QA Reviewers' },
    });
    fireEvent.click(screen.getByTestId('tenant-group-rename-submit-button'));

    await waitFor(() => {
      expect(mockRenameTenantGroup).toHaveBeenCalledWith('t1', 'reviewers', 'QA Reviewers');
    });
  });

  it('deletes a group and keeps members in the tenant', async () => {
    mockDeleteTenantGroup.mockResolvedValue(undefined);
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.mouseDown(screen.getByRole('tab', { name: /Groups/ }));
    fireEvent.click(await screen.findByTestId('tenant-group-remove-button-reviewers'));
    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => {
      expect(mockDeleteTenantGroup).toHaveBeenCalledWith('t1', 'reviewers');
    });
    expect(mockRemoveTenantMember).not.toHaveBeenCalled();
  });

  it('grants and revokes tenant roles on a group', async () => {
    mockGrantTenantGroupRole.mockResolvedValue({
      tenant_id: 't1',
      group_name: 'reviewers',
      role_name: 'submitter',
      group: { ...GROUPS.groups[1], mapped_roles: ['reviewer', 'submitter'] },
    });
    mockRevokeTenantGroupRole.mockResolvedValue({
      tenant_id: 't1',
      group_name: 'reviewers',
      role_name: 'reviewer',
      group: { ...GROUPS.groups[1], mapped_roles: [] },
    });
    renderWithOutlet({ canManageTenant: true });
    await screen.findByText('Ed Itor');

    fireEvent.mouseDown(screen.getByRole('tab', { name: /Groups/ }));
    fireEvent.click(await screen.findByTestId('tenant-group-manage-roles-button-reviewers'));
    expect(await screen.findByRole('heading', { name: 'Group roles' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('tenant-group-role-checkbox-reviewers-submitter'));
    fireEvent.click(screen.getByTestId('tenant-group-role-checkbox-reviewers-reviewer'));

    await waitFor(() => {
      expect(mockGrantTenantGroupRole).toHaveBeenCalledWith('t1', 'reviewers', 'submitter');
      expect(mockRevokeTenantGroupRole).toHaveBeenCalledWith('t1', 'reviewers', 'reviewer');
    });
  });

  it('renames the tenant display name', async () => {
    mockUpdateTenantName.mockResolvedValue(undefined);
    renderWithOutlet({ canManageTenant: true, isSuperAdmin: false });
    await screen.findByText('Ed Itor');

    fireEvent.click(screen.getByTestId('tenant-management-edit-button'));
    fireEvent.change(screen.getByTestId('tenant-name'), { target: { value: 'Acme West' } });
    fireEvent.click(screen.getByTestId('tenant-save'));

    await waitFor(() => {
      expect(mockUpdateTenantName).toHaveBeenCalledWith('t1', 'Acme West');
    });
  });

  it('lets a super-admin create an invitation and surfaces a local accept link', async () => {
    mockCreateTenantInvitation.mockResolvedValue({
      tenant_id: 't1',
      invitation: {
        id: 'inv1',
        tenant_id: 't1',
        email: 'new@example.com',
        roles: ['editor'],
        status: 'PENDING',
        expires_at_in_seconds: 1_900_000_000,
        created_by: 'admin',
        created_at_in_seconds: 1_800_000_000,
        invitation_link: 'http://localhost:6853/accept-invitation?token=abc',
      },
    });
    renderWithOutlet(
      {
        canManageTenant: true,
        isSuperAdmin: true,
        scopedTenantId: null,
        selectedTenantId: null,
        tenants: [{ id: 't1', name: 'Acme Corp' }],
      },
      '/tenant-management/t1',
    );
    await screen.findByText('Ed Itor');

    fireEvent.click(screen.getByTestId('tenant-invite-user-button'));
    fireEvent.change(screen.getByTestId('invite-user-email-input'), {
      target: { value: 'new@example.com' },
    });
    fireEvent.click(screen.getByTestId('invite-user-role-editor'));
    fireEvent.click(screen.getByTestId('invite-user-submit'));

    await waitFor(() => {
      expect(mockCreateTenantInvitation).toHaveBeenCalledWith('t1', {
        email: 'new@example.com',
        roles: ['editor'],
        validity_days: 7,
      });
    });
    expect(
      await screen.findByDisplayValue('http://localhost:6853/accept-invitation?token=abc'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('invite-user-submit')).not.toBeInTheDocument();
  });

  it('lists invitations and lets a super-admin resend or revoke', async () => {
    mockFetchTenantInvitations.mockResolvedValue({
      tenant_id: 't1',
      results: [
        {
          id: 'inv1',
          tenant_id: 't1',
          email: 'pending@example.com',
          roles: ['editor'],
          status: 'PENDING',
          expires_at_in_seconds: 1_900_000_000,
          created_by: 'admin',
          created_at_in_seconds: 1_800_000_000,
        },
        {
          id: 'inv2',
          tenant_id: 't1',
          email: 'done@example.com',
          roles: ['viewer'],
          status: 'ACCEPTED',
          expires_at_in_seconds: 1_900_000_000,
          created_by: 'admin',
          created_at_in_seconds: 1_800_000_000,
        },
      ],
      total: 2,
      offset: 0,
      limit: 100,
    });
    mockResendTenantInvitation.mockResolvedValue({
      tenant_id: 't1',
      invitation: { id: 'inv1', status: 'PENDING' },
    });
    mockRevokeTenantInvitation.mockResolvedValue({
      tenant_id: 't1',
      invitation: { id: 'inv1', status: 'REVOKED' },
    });
    renderWithOutlet(
      {
        canManageTenant: true,
        isSuperAdmin: true,
        scopedTenantId: null,
        selectedTenantId: null,
        tenants: [{ id: 't1', name: 'Acme Corp' }],
      },
      '/tenant-management/t1',
    );

    expect(await screen.findByText('pending@example.com')).toBeInTheDocument();
    expect(screen.getByText('done@example.com')).toBeInTheDocument();
    expect(screen.getByText('PENDING')).toBeInTheDocument();
    expect(screen.getByText('ACCEPTED')).toBeInTheDocument();
    expect(screen.getByTestId('invitation-resend-inv2')).toBeDisabled();
    expect(screen.getByTestId('invitation-revoke-inv2')).toBeDisabled();

    fireEvent.click(screen.getByTestId('invitation-resend-inv1'));
    await waitFor(() => {
      expect(mockResendTenantInvitation).toHaveBeenCalledWith('t1', 'inv1');
    });
    fireEvent.click(screen.getByTestId('invitation-revoke-inv1'));
    await waitFor(() => {
      expect(mockRevokeTenantInvitation).toHaveBeenCalledWith('t1', 'inv1');
    });
  });
});

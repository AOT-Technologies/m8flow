import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantPage from "./TenantPage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const messages: Record<string, string> = {
        organization_management: "Tenant Management",
        organization_management_description:
          "Manage the Keycloak tenants that back access in Keycloak.",
        add_organization: "Add Tenant",
        edit_organization: "Edit Tenant",
        manage_tenant_groups: "Manage Tenant Groups",
        tenant_group_management_description:
          "Review tenant users, add existing members, and manage the Keycloak groups and tenant-scoped roles associated with this tenant.",
        delete_organization: "Delete Tenant",
        search_by: "Search By",
        organization_alias: "Tenant Alias",
        organization_name: "Tenant Name",
        filter_by_status: "Filter by Status",
        all: "All",
        active: "Active",
        inactive: "Inactive",
        status: "Status",
        actions: "Actions",
        cancel: "Cancel",
        create: "Create",
        save: "Save",
        processing: "Processing...",
        organization_created_successfully: "Tenant created successfully.",
        organization_updated_successfully: "Tenant updated successfully.",
        organization_alias_already_exists: "Tenant alias already exists",
        organization_alias_cannot_be_empty: "Tenant alias cannot be empty",
        organization_alias_invalid_pattern:
          "Tenant alias can only contain letters, numbers, hyphens, and underscores",
        organization_name_cannot_be_empty: "Tenant name cannot be empty",
        failed_to_create_organization:
          "Failed to create tenant. Please try again.",
        failed_to_update_organization:
          "Failed to update tenant. Please try again.",
        failed_to_delete_organization:
          "Failed to delete tenant. Please try again.",
        failed_to_load_tenant_groups: "Failed to load tenant groups.",
        search_tenant_groups: "Search tenant groups or members...",
        refresh_tenant_groups: "Refresh tenant groups",
        no_tenant_groups_found: "No tenant groups found.",
        no_organization_members_found: "No tenant members found.",
        group: "Group",
        groups: "Groups",
        members: "Members",
        granted_roles: "Granted Roles",
        username: "Username",
        display_name: "Display Name",
        email: "Email",
        add_tenant_user: "Add User",
        tenant_role_tenant_admin: "Tenant Admin",
        tenant_role_editor: "Editor",
        tenant_role_integrator: "Integrator",
        tenant_role_reviewer: "Reviewer",
        tenant_role_submitter: "Submitter",
        tenant_role_viewer: "Viewer",
      };

      if (key === "organization_alias_max_length") {
        return `Tenant alias must be ${options?.count ?? ""} characters or fewer`;
      }
      if (key === "organization_name_max_length") {
        return `Tenant name must be ${options?.count ?? ""} characters or fewer`;
      }
      if (key === "showing_organizations_count") {
        return `Showing ${options?.filtered ?? 0} of ${options?.total ?? 0} tenant(s)`;
      }
      if (key === "search_by_placeholder") {
        return `Search by ${options?.type ?? "name"}...`;
      }

      return messages[key] ?? key;
    },
  }),
}));

vi.mock("@mui/icons-material", () => ({
  Search: () => <svg data-testid="icon-search" />,
  Edit: () => <svg data-testid="icon-edit" />,
  Clear: () => <svg data-testid="icon-clear" />,
  Add: () => <svg data-testid="icon-add" />,
  ManageAccounts: () => <svg data-testid="icon-manage-accounts" />,
}));

const mockUseTenants = vi.fn();
const mockUsePermissionFetcher = vi.fn();
const mockCreateTenant = vi.fn();
const mockGetTenantGroups = vi.fn();
const mockGetTenantMembers = vi.fn();

vi.mock("../hooks/useTenants", () => ({
  useTenants: () => mockUseTenants(),
}));

vi.mock("@spiffworkflow-frontend/hooks/PermissionService", () => ({
  usePermissionFetcher: () => mockUsePermissionFetcher(),
}));

vi.mock("../services/TenantService", () => ({
  TENANT_MEMBER_ROLES: [
    "tenant-admin",
    "editor",
    "integrator",
    "reviewer",
    "submitter",
    "viewer",
  ],
  default: {
    createTenant: (...args: unknown[]) => mockCreateTenant(...args),
    getTenantGroups: (...args: unknown[]) => mockGetTenantGroups(...args),
    getTenantMembers: (...args: unknown[]) => mockGetTenantMembers(...args),
    getAvailableTenantUsers: vi.fn(),
    addTenantMember: vi.fn(),
    addTenantMemberToGroup: vi.fn(),
    removeTenantMemberFromGroup: vi.fn(),
    assignTenantGroupRole: vi.fn(),
    removeTenantGroupRole: vi.fn(),
    updateTenant: vi.fn(),
    deleteTenant: vi.fn(),
  },
}));

describe("TenantPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTenantGroups.mockResolvedValue([]);
    mockGetTenantMembers.mockResolvedValue([]);
  });

  it("creates a tenant from the add tenant modal", async () => {
    const refetch = vi.fn();
    mockUseTenants.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      refetch,
    });
    mockUsePermissionFetcher.mockReturnValue({
      ability: { can: () => true },
      permissionsLoaded: true,
    });
    mockCreateTenant.mockResolvedValue({
      alias: "it-team_1",
      name: "Information Technology",
      organization_id: "tenant-uuid",
      id: "tenant-uuid",
    });

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-add-button"));
    await screen.findByTestId("tenant-modal-dialog");

    fireEvent.change(screen.getByLabelText("Tenant Alias"), {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByLabelText("Tenant Name"), {
      target: { value: "Information Technology" },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    await waitFor(() => {
      expect(mockCreateTenant).toHaveBeenCalledWith({
        slug: "it-team_1",
        name: "Information Technology",
      });
    });

    await waitFor(() => {
      expect(refetch).toHaveBeenCalled();
    });

    expect(
      await screen.findByText("Tenant created successfully."),
    ).toBeInTheDocument();
  });

  it("shows inline validation errors instead of submitting an empty tenant form", async () => {
    mockUseTenants.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUsePermissionFetcher.mockReturnValue({
      ability: { can: () => true },
      permissionsLoaded: true,
    });

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-add-button"));
    await screen.findByTestId("tenant-modal-dialog");
    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText("Tenant alias cannot be empty"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Tenant name cannot be empty"),
    ).toBeInTheDocument();
    expect(mockCreateTenant).not.toHaveBeenCalled();
  });

  it("validates slug format and display name length before submit", async () => {
    mockUseTenants.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUsePermissionFetcher.mockReturnValue({
      ability: { can: () => true },
      permissionsLoaded: true,
    });

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-add-button"));
    await screen.findByTestId("tenant-modal-dialog");

    fireEvent.change(screen.getByLabelText("Tenant Alias"), {
      target: { value: "it team" },
    });
    fireEvent.change(screen.getByLabelText("Tenant Name"), {
      target: { value: "A".repeat(51) },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText(
        "Tenant alias can only contain letters, numbers, hyphens, and underscores",
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Tenant name must be 50 characters or fewer"),
    ).toBeInTheDocument();
    expect(mockCreateTenant).not.toHaveBeenCalled();
  });

  it("shows a slug validation error when the tenant slug already exists", async () => {
    mockUseTenants.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUsePermissionFetcher.mockReturnValue({
      ability: { can: () => true },
      permissionsLoaded: true,
    });
    mockCreateTenant.mockRejectedValue({
      detail: "Organization already exists or conflict",
    });

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-add-button"));
    await screen.findByTestId("tenant-modal-dialog");
    fireEvent.change(screen.getByLabelText("Tenant Alias"), {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByLabelText("Tenant Name"), {
      target: { value: "Information Technology" },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText("Tenant alias already exists"),
    ).toBeInTheDocument();
  });

  it("opens tenant group management and loads dynamic keycloak groups", async () => {
    mockUseTenants.mockReturnValue({
      data: [
        {
          id: "tenant-uuid",
          name: "Information Technology",
          slug: "it",
          status: "ACTIVE",
          createdBy: "system",
          modifiedBy: "system",
          createdAtInSeconds: 1,
          updatedAtInSeconds: 1,
        },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUsePermissionFetcher.mockReturnValue({
      ability: { can: () => true },
      permissionsLoaded: true,
    });
    mockGetTenantGroups.mockResolvedValue([
      {
        id: "group-admin",
        name: "Administrators",
        path: "/Administrators",
        mapped_roles: ["tenant-admin"],
        member_count: 1,
        members: [
          {
            id: "member-1",
            username: "admin",
            email: "admin@example.com",
            display_name: "Admin User",
          },
        ],
      },
      {
        id: "group-approvers",
        name: "Approvers",
        path: "/Approvers",
        mapped_roles: ["reviewer"],
        member_count: 1,
        members: [
          {
            id: "member-2",
            username: "reviewer",
            email: null,
            display_name: "Reviewer User",
          },
        ],
      },
    ]);
    mockGetTenantMembers.mockResolvedValue([
      {
        id: "member-1",
        username: "admin",
        email: "admin@example.com",
        display_name: "Admin User",
        roles: ["tenant-admin"],
      },
      {
        id: "member-2",
        username: "reviewer",
        email: null,
        display_name: "Reviewer User",
        roles: ["reviewer"],
      },
    ]);

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-roles-button-tenant-uuid"));

    expect(
      await screen.findByText(
        "Review tenant users, add existing members, and manage the Keycloak groups and tenant-scoped roles associated with this tenant.",
      ),
    ).toBeInTheDocument();
    expect(mockGetTenantGroups).toHaveBeenCalledWith("tenant-uuid");
    expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-uuid");
    expect(screen.getAllByText("Administrators").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Approvers").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Tenant Admin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Reviewer").length).toBeGreaterThan(0);
    expect(screen.getAllByText("admin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("reviewer").length).toBeGreaterThan(0);
  });

  it("filters tenant groups by member or group name inside the dialog", async () => {
    mockUseTenants.mockReturnValue({
      data: [
        {
          id: "tenant-uuid",
          name: "Information Technology",
          slug: "it",
          status: "ACTIVE",
          createdBy: "system",
          modifiedBy: "system",
          createdAtInSeconds: 1,
          updatedAtInSeconds: 1,
        },
      ],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUsePermissionFetcher.mockReturnValue({
      ability: { can: () => true },
      permissionsLoaded: true,
    });
    mockGetTenantGroups.mockResolvedValue([
      {
        id: "group-designers",
        name: "Designers",
        path: "/Designers",
        mapped_roles: ["editor"],
        member_count: 1,
        members: [
          {
            id: "member-1",
            username: "editor",
            email: null,
            display_name: "Editor User",
          },
        ],
      },
      {
        id: "group-support",
        name: "Support",
        path: "/Support",
        mapped_roles: ["integrator"],
        member_count: 1,
        members: [
          {
            id: "member-2",
            username: "integrator",
            email: null,
            display_name: "Integrator User",
          },
        ],
      },
    ]);
    mockGetTenantMembers.mockResolvedValue([
      {
        id: "member-1",
        username: "editor",
        email: null,
        display_name: "Editor User",
        roles: ["editor"],
      },
      {
        id: "member-2",
        username: "integrator",
        email: null,
        display_name: "Integrator User",
        roles: ["integrator"],
      },
    ]);

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-roles-button-tenant-uuid"));
    await screen.findAllByText("Designers");

    fireEvent.change(screen.getByPlaceholderText("Search tenant groups or members..."), {
      target: { value: "integrator" },
    });

    expect(screen.getAllByText("Designers").length).toBe(1);
    expect(screen.getAllByText("Support").length).toBeGreaterThan(0);
  });
});

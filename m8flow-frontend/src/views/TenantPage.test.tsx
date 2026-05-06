import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantPage from "./TenantPage";

const mockUseTenants = vi.fn();
const mockUsePermissionFetcher = vi.fn();
const mockCreateTenant = vi.fn();
const mockGetTenantMembers = vi.fn();
const mockAssignTenantMemberRole = vi.fn();
const mockRemoveTenantMemberRole = vi.fn();

vi.mock("../hooks/useTenants", () => ({
  useTenants: () => mockUseTenants(),
}));

vi.mock("@spiffworkflow-frontend/hooks/PermissionService", () => ({
  usePermissionFetcher: () => mockUsePermissionFetcher(),
}));

vi.mock("../services/TenantService", () => ({
  default: {
    createTenant: (...args: unknown[]) => mockCreateTenant(...args),
    getTenantMembers: (...args: unknown[]) => mockGetTenantMembers(...args),
    assignTenantMemberRole: (...args: unknown[]) =>
      mockAssignTenantMemberRole(...args),
    removeTenantMemberRole: (...args: unknown[]) =>
      mockRemoveTenantMemberRole(...args),
    updateTenant: vi.fn(),
    deleteTenant: vi.fn(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const messages: Record<string, string> = {
        organization_management: "Organization Management",
        organization_management_description:
          "Manage the Keycloak organizations that back tenant access in the shared realm.",
        add_organization: "Add Organization",
        edit_organization: "Edit Organization",
        manage_organization_roles: "Manage Organization Roles",
        organization_role_management_description:
          "Assign tenant-scoped roles to members of this Keycloak organization. Only organization members are listed here.",
        delete_organization: "Delete Organization",
        search_by: "Search By",
        name: "Name",
        organization_alias: "Organization Alias",
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
        organization_name: "Organization Name",
        organization_created_successfully:
          "Organization created successfully.",
        organization_updated_successfully:
          "Organization updated successfully.",
        organization_alias_already_exists:
          "Organization alias already exists",
        organization_alias_cannot_be_empty:
          "Organization alias cannot be empty",
        organization_alias_invalid_pattern:
          "Organization alias can only contain letters, numbers, hyphens, and underscores",
        organization_name_cannot_be_empty:
          "Organization name cannot be empty",
        failed_to_load_organization_members:
          "Failed to load organization members.",
        failed_to_update_organization_role:
          "Failed to update organization role.",
        search_organization_members: "Search organization members...",
        refresh_members: "Refresh members",
        no_organization_members_found: "No organization members found.",
        username: "Username",
        email: "Email",
        tenant_role_tenant_admin: "Tenant Admin",
        tenant_role_editor: "Editor",
        tenant_role_integrator: "Integrator",
        tenant_role_reviewer: "Reviewer",
        tenant_role_viewer: "Viewer",
        failed_to_create_organization:
          "Failed to create organization. Please try again.",
        failed_to_update_organization:
          "Failed to update organization. Please try again.",
        failed_to_delete_organization:
          "Failed to delete organization. Please try again.",
      };

      if (key === "organization_alias_max_length") {
        return `Organization alias must be ${options?.count ?? ""} characters or fewer`;
      }
      if (key === "organization_name_max_length") {
        return `Organization name must be ${options?.count ?? ""} characters or fewer`;
      }
      if (key === "showing_organizations_count") {
        return `Showing ${options?.filtered ?? 0} of ${options?.total ?? 0} organization(s)`;
      }
      if (key === "search_by_placeholder") {
        return `Search by ${options?.type ?? "name"}...`;
      }

      return messages[key] ?? key;
    },
  }),
}));

describe("TenantPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTenantMembers.mockResolvedValue([]);
    mockAssignTenantMemberRole.mockResolvedValue({
      id: "member-1",
      username: "editor",
      email: "editor@example.com",
      display_name: "Editor User",
      roles: ["editor"],
    });
    mockRemoveTenantMemberRole.mockResolvedValue({
      id: "member-1",
      username: "editor",
      email: "editor@example.com",
      display_name: "Editor User",
      roles: [],
    });
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

    fireEvent.change(screen.getByLabelText("Organization Alias"), {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByLabelText("Organization Name"), {
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
      await screen.findByText("Organization created successfully."),
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
    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText("Organization alias cannot be empty"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Organization name cannot be empty"),
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

    fireEvent.change(screen.getByLabelText("Organization Alias"), {
      target: { value: "it team" },
    });
    fireEvent.change(screen.getByLabelText("Organization Name"), {
      target: { value: "A".repeat(51) },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText(
        "Organization alias can only contain letters, numbers, hyphens, and underscores",
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Organization name must be 50 characters or fewer"),
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
    fireEvent.change(screen.getByLabelText("Organization Alias"), {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByLabelText("Organization Name"), {
      target: { value: "Information Technology" },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText("Organization alias already exists"),
    ).toBeInTheDocument();
  });

  it("opens organization role management and assigns a tenant role", async () => {
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
    mockGetTenantMembers.mockResolvedValue([
      {
        id: "member-1",
        username: "editor",
        email: "editor@example.com",
        display_name: "Editor User",
        roles: [],
      },
    ]);

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-roles-button-tenant-uuid"));

    expect(
      await screen.findByText(
        "Assign tenant-scoped roles to members of this Keycloak organization. Only organization members are listed here.",
      ),
    ).toBeInTheDocument();
    expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-uuid");

    fireEvent.click(
      await screen.findByRole("checkbox", { name: "editor-editor" }),
    );

    await waitFor(() => {
      expect(mockAssignTenantMemberRole).toHaveBeenCalledWith(
        "tenant-uuid",
        "editor",
        "editor",
      );
    });
  });

  it("does not submit the same organization role toggle twice while pending", async () => {
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
    mockGetTenantMembers.mockResolvedValue([
      {
        id: "member-1",
        username: "admin",
        email: "admin@example.com",
        display_name: "Admin User",
        roles: [],
      },
    ]);

    let resolveAssign: ((value: unknown) => void) | null = null;
    mockAssignTenantMemberRole.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveAssign = resolve;
        }),
    );

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-roles-button-tenant-uuid"));

    const tenantAdminCheckbox = await screen.findByRole("checkbox", {
      name: "admin-tenant-admin",
    });

    fireEvent.click(tenantAdminCheckbox);
    fireEvent.click(tenantAdminCheckbox);

    expect(mockAssignTenantMemberRole).toHaveBeenCalledTimes(1);

    resolveAssign?.({
      id: "member-1",
      username: "admin",
      email: "admin@example.com",
      display_name: "Admin User",
      roles: ["tenant-admin"],
    });

    await waitFor(() => {
      expect(
        screen.getByRole("checkbox", { name: "admin-tenant-admin" }),
      ).toBeChecked();
    });
  });
});

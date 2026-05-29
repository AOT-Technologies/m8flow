import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantManagementPage from "./TenantManagementPage";

const mockGetTenantGroups = vi.fn();
const mockGetTenantMembers = vi.fn();
const mockUpdateTenant = vi.fn();
const mockRememberTenantDisplayName = vi.fn();

vi.mock("../services/UserService", () => ({
  default: {
    getTenantId: () => "tenant-1",
    getTenantName: () => "Tenant One",
    getOrganizationMemberships: () => [
      {
        alias: "tenant-one",
        id: "tenant-1",
        name: "Tenant One",
      },
    ],
    rememberTenantDisplayName: (...args: unknown[]) =>
      mockRememberTenantDisplayName(...args),
  },
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
    getTenantGroups: (...args: unknown[]) => mockGetTenantGroups(...args),
    getTenantMembers: (...args: unknown[]) => mockGetTenantMembers(...args),
    getAvailableTenantUsers: vi.fn(),
    addTenantMember: vi.fn(),
    createTenantGroup: vi.fn(),
    addTenantMemberToGroup: vi.fn(),
    removeTenantMemberFromGroup: vi.fn(),
    assignTenantGroupRole: vi.fn(),
    removeTenantGroupRole: vi.fn(),
    updateTenant: (...args: unknown[]) => mockUpdateTenant(...args),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const messages: Record<string, string> = {
        tenant_management: "Tenant Management",
        edit_organization: "Edit Tenant",
        tenant_group_management_description:
          "Review tenant users, add existing members, and manage the Keycloak groups and tenant-scoped roles associated with this tenant.",
        manage_tenant_groups: "Manage Tenant Groups",
        search_tenant_groups: "Search tenant groups or members...",
        refresh_tenant_groups: "Refresh tenant groups",
        members: "Members",
        groups: "Groups",
        group: "Group",
        granted_roles: "Granted Roles",
        username: "Username",
        display_name: "Display Name",
        email: "Email",
        add_tenant_user: "Add User",
        create_group: "Create Group",
        create_group_description:
          "Create a new Keycloak group for this tenant. Tenant roles can be assigned after creation.",
        group_name: "Group Name",
        create_tenant_user: "Add User to Tenant",
        add_tenant_user_description:
          "Add an existing user to this tenant, then assign Keycloak groups.",
        existing_user: "Existing User",
        search_existing_users: "Search existing users...",
        no_available_users_found: "No existing users available to add.",
        failed_to_create_tenant_group: "Failed to create tenant group.",
        organization_name: "Tenant Name",
        save: "Save",
        cancel: "Cancel",
        processing: "Processing...",
      };
      return messages[key] ?? key;
    },
  }),
}));

describe("TenantManagementPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTenantGroups.mockResolvedValue([
      {
        id: "group-approvers",
        name: "Approvers",
        path: "/Approvers",
        mapped_roles: ["reviewer"],
        member_count: 1,
        members: [
          {
            id: "member-1",
            username: "reviewer",
            email: "reviewer@example.com",
            display_name: "Reviewer User",
          },
        ],
      },
    ]);
    mockGetTenantMembers.mockResolvedValue([
      {
        id: "member-1",
        username: "reviewer",
        email: "reviewer@example.com",
        display_name: "Reviewer User",
        roles: ["reviewer"],
      },
    ]);
    mockUpdateTenant.mockResolvedValue({
      id: "tenant-1",
      name: "Tenant One Updated",
    });
  });

  it("renders tenant management for the current tenant and remembers the updated display name after rename", async () => {
    render(<TenantManagementPage />);

    expect(screen.getByText("Tenant Management")).toBeInTheDocument();
    expect(await screen.findByText("Reviewer User")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-role-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tenant-management-edit-button"));

    expect(await screen.findByTestId("tenant-modal-dialog")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Tenant One")).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("Tenant One"), {
      target: { value: "Tenant One Updated" },
    });
    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(await screen.findByText("Tenant updated successfully.")).toBeInTheDocument();
    expect(mockRememberTenantDisplayName).toHaveBeenCalledWith({
      id: "tenant-1",
      alias: "tenant-one",
      name: "Tenant One Updated",
    });
  });
});

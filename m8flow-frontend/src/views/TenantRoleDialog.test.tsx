import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantRoleDialog from "./TenantRoleDialog";

const mockGetTenantGroups = vi.fn();
const mockGetTenantMembers = vi.fn();
const mockGetAvailableTenantUsers = vi.fn();
const mockAddTenantMember = vi.fn();
const mockCreateTenantGroup = vi.fn();
const mockAddTenantMemberToGroup = vi.fn();
const mockRemoveTenantMemberFromGroup = vi.fn();
const mockAssignTenantGroupRole = vi.fn();
const mockRemoveTenantGroupRole = vi.fn();

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
    getAvailableTenantUsers: (...args: unknown[]) =>
      mockGetAvailableTenantUsers(...args),
    addTenantMember: (...args: unknown[]) => mockAddTenantMember(...args),
    createTenantGroup: (...args: unknown[]) => mockCreateTenantGroup(...args),
    addTenantMemberToGroup: (...args: unknown[]) =>
      mockAddTenantMemberToGroup(...args),
    removeTenantMemberFromGroup: (...args: unknown[]) =>
      mockRemoveTenantMemberFromGroup(...args),
    assignTenantGroupRole: (...args: unknown[]) =>
      mockAssignTenantGroupRole(...args),
    removeTenantGroupRole: (...args: unknown[]) =>
      mockRemoveTenantGroupRole(...args),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const messages: Record<string, string> = {
        manage_tenant_groups: "Manage Tenant Groups",
        tenant_group_management_description:
          "Review tenant users, add existing members, and manage the Keycloak groups and tenant-scoped roles associated with this tenant.",
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
        create_tenant_user: "Add User to Tenant",
        add_tenant_user_description:
          "Add an existing user to this tenant, then assign Keycloak groups.",
        group_name: "Group Name",
        failed_to_create_tenant_group: "Failed to create tenant group.",
        existing_user: "Existing User",
        search_existing_users: "Search existing users...",
        no_available_users_found: "No existing users available to add.",
        tenant_role_reviewer: "Reviewer",
        tenant_role_submitter: "Submitter",
        cancel: "Cancel",
        add: "Add",
        processing: "Processing...",
      };
      return messages[key] ?? key;
    },
  }),
}));

describe("TenantRoleDialog", () => {
  const tenant = {
    id: "tenant-1",
    name: "Tenant One",
    slug: "tenant-one",
    status: "ACTIVE" as const,
    createdBy: "system",
    modifiedBy: "system",
    createdAtInSeconds: 1,
    updatedAtInSeconds: 1,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTenantGroups.mockResolvedValue([
      {
        id: "group-approvers",
        name: "Approvers",
        path: "/Approvers",
        mapped_roles: ["reviewer"],
        member_count: 0,
        members: [],
      },
      {
        id: "group-submitters",
        name: "Submitters",
        path: "/Submitters",
        mapped_roles: ["submitter"],
        member_count: 1,
        members: [
          {
            id: "member-3",
            username: "submitter",
            email: "submitter@example.com",
            display_name: "Submitter User",
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
      {
        id: "member-3",
        username: "submitter",
        email: "submitter@example.com",
        display_name: "Submitter User",
        roles: ["submitter"],
      },
    ]);
    mockGetAvailableTenantUsers.mockResolvedValue([
      {
        id: "member-2",
        username: "new.user",
        email: "new.user@example.com",
        display_name: "New User",
      },
    ]);
    mockAddTenantMember.mockResolvedValue({
      id: "member-2",
      username: "new.user",
      email: "new.user@example.com",
      display_name: "new.user",
      roles: ["reviewer"],
    });
    mockCreateTenantGroup.mockResolvedValue({
      id: "group-manager",
      name: "Manager",
      path: "/Manager",
      mapped_roles: [],
      member_count: 0,
      members: [],
    });
    mockAddTenantMemberToGroup.mockResolvedValue({
      id: "member-1",
      username: "reviewer",
      email: "reviewer@example.com",
      display_name: "Reviewer User",
      roles: ["reviewer"],
    });
    mockRemoveTenantMemberFromGroup.mockResolvedValue({
      id: "member-1",
      username: "reviewer",
      email: "reviewer@example.com",
      display_name: "Reviewer User",
      roles: [],
    });
    mockAssignTenantGroupRole.mockResolvedValue({
      id: "group-approvers",
      name: "Approvers",
      path: "/Approvers",
      mapped_roles: ["reviewer"],
      member_count: 0,
      members: [],
    });
    mockRemoveTenantGroupRole.mockResolvedValue({
      id: "group-approvers",
      name: "Approvers",
      path: "/Approvers",
      mapped_roles: [],
      member_count: 0,
      members: [],
    });
  });

  it("adds a tenant member with selected groups", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByText("Reviewer User");
    fireEvent.click(screen.getByTestId("tenant-member-add-button"));
    await screen.findByText("Add User to Tenant: Tenant One");

    await screen.findByText("New User");
    fireEvent.click(
      screen.getByTestId("tenant-member-existing-user-option-new.user"),
    );
    fireEvent.click(screen.getByTestId("tenant-member-group-option-Approvers"));
    fireEvent.click(screen.getByTestId("tenant-member-submit-button"));

    await waitFor(() =>
      expect(mockAddTenantMember).toHaveBeenCalledWith("tenant-1", {
        username: "new.user",
        group_names: ["Approvers"],
      }),
    );
  });

  it("does not render the group path below the group name", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    expect(screen.queryByText("/Approvers")).not.toBeInTheDocument();
  });

  it("toggles tenant group membership from the member matrix", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByText("Reviewer User");
    fireEvent.click(
      screen.getByTestId("tenant-group-checkbox-reviewer-Approvers"),
    );

    await waitFor(() =>
      expect(mockAddTenantMemberToGroup).toHaveBeenCalledWith(
        "tenant-1",
        "reviewer",
        "Approvers",
      ),
    );
  });

  it("toggles tenant roles from the group matrix", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByText("Reviewer User");
    fireEvent.click(
      screen.getByTestId("tenant-group-role-checkbox-Approvers-viewer"),
    );

    await waitFor(() =>
      expect(mockAssignTenantGroupRole).toHaveBeenCalledWith(
        "tenant-1",
        "Approvers",
        "viewer",
      ),
    );
  });

  it("renders the submitter granted role when returned by the backend", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    expect(await screen.findAllByText("Submitter")).not.toHaveLength(0);
    expect(screen.getAllByText("Submitters").length).toBeGreaterThan(0);
  });

  it("creates a tenant group from the dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByText("Reviewer User");
    fireEvent.click(screen.getByTestId("tenant-group-add-button"));
    fireEvent.change(screen.getByTestId("tenant-group-name-input"), {
      target: { value: "Manager" },
    });
    fireEvent.click(screen.getByTestId("tenant-group-submit-button"));

    await waitFor(() =>
      expect(mockCreateTenantGroup).toHaveBeenCalledWith("tenant-1", {
        name: "Manager",
      }),
    );
  });
});

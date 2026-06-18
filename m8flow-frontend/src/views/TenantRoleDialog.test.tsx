import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantRoleDialog from "./TenantRoleDialog";

const mockGetTenantGroups = vi.fn();
const mockGetTenantGroupsPage = vi.fn();
const mockGetTenantMembers = vi.fn();
const mockGetAvailableTenantUsers = vi.fn();
const mockAddTenantMember = vi.fn();
const mockCreateTenantGroup = vi.fn();
const mockRenameTenantGroup = vi.fn();
const mockDeleteTenantGroup = vi.fn();
const mockAddTenantMemberToGroup = vi.fn();
const mockRemoveTenantMemberFromGroup = vi.fn();
const mockAssignTenantGroupRole = vi.fn();
const mockRemoveTenantGroupRole = vi.fn();

vi.mock("../services/TenantService", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/TenantService")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      getTenantGroups: (...args: unknown[]) => mockGetTenantGroups(...args),
      getTenantGroupsPage: (...args: unknown[]) => mockGetTenantGroupsPage(...args),
      getTenantMembers: (...args: unknown[]) => mockGetTenantMembers(...args),
      getTenantMembersPage: (...args: unknown[]) => mockGetTenantMembers(...args),
      getAvailableTenantUsers: (...args: unknown[]) =>
        mockGetAvailableTenantUsers(...args),
      getAvailableTenantUsersPage: (...args: unknown[]) =>
        mockGetAvailableTenantUsers(...args),
      addTenantMember: (...args: unknown[]) => mockAddTenantMember(...args),
      createTenantGroup: (...args: unknown[]) => mockCreateTenantGroup(...args),
      renameTenantGroup: (...args: unknown[]) => mockRenameTenantGroup(...args),
      deleteTenantGroup: (...args: unknown[]) => mockDeleteTenantGroup(...args),
      addTenantMemberToGroup: (...args: unknown[]) =>
        mockAddTenantMemberToGroup(...args),
      removeTenantMemberFromGroup: (...args: unknown[]) =>
        mockRemoveTenantMemberFromGroup(...args),
      assignTenantGroupRole: (...args: unknown[]) =>
        mockAssignTenantGroupRole(...args),
      removeTenantGroupRole: (...args: unknown[]) =>
        mockRemoveTenantGroupRole(...args),
    },
  };
});

vi.mock("react-i18next", () => ({
  initReactI18next: {
    type: "3rdParty",
    init: () => undefined,
  },
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (key === "tenant_groups_page_indicator") {
        return `Page ${options?.page ?? ""}`;
      }
      const messages: Record<string, string> = {
        manage_tenant_groups: "Manage Tenant Groups",
        tenant_group_management_description:
          "Add existing users as members and manage groups and roles associated with this tenant.",
        search_organization_members: "Search tenant members...",
        search_tenant_members_minimum_characters:
          "Type at least 3 characters to search tenant members.",
        search_tenant_groups: "Search tenant groups or members...",
        refresh_tenant_groups: "Refresh tenant groups",
        members: "Members",
        groups: "Groups",
        group: "Group",
        action: "Action",
        granted_roles: "Granted Roles",
        username: "Username",
        display_name: "Display Name",
        email: "Email",
        effective_roles: "Effective Roles",
        add_tenant_user: "Add Member",
        manage_member_groups: "Manage Member Groups",
        manage_member_groups_description:
          "Add or remove this member from tenant groups.",
        manage_granted_roles: "Manage Granted Roles",
        manage_granted_roles_description:
          "Grant or revoke tenant roles for this group.",
        rename_tenant_group: "Rename Group",
        rename_tenant_group_description:
          "Change this group's name while keeping its members and granted roles.",
        remove_tenant_member: "Remove Member",
        remove_tenant_member_confirmation:
          "Remove this member from all tenant groups?",
        remove_tenant_member_unavailable:
          "This member is not assigned to any groups.",
        remove_tenant_group: "Remove Group",
        remove_tenant_group_confirmation:
          "Remove this group from the tenant? Members will remain in the tenant, but any roles granted through this group will be removed.",
        no_groups_assigned: "No groups",
        no_effective_roles_assigned: "No effective roles",
        no_granted_roles_assigned: "No granted roles",
        create_group: "Create Group",
        create_group_description:
          "Create a new Keycloak group for this tenant. Tenant roles can be assigned after creation.",
        create_tenant_user: "Add User to Tenant",
        add_tenant_user_description:
          "Add an existing user to this tenant, then assign groups.",
        failed_to_remove_tenant_member: "Failed to remove tenant member.",
        failed_to_remove_tenant_group: "Failed to remove tenant group.",
        group_name: "Group Name",
        tenant_group_name_exists: "Group '{{name}}' already exists in this tenant.",
        tenant_group_name_helper:
          "Up to 64 characters. Letters, numbers, spaces, hyphens, and underscores only.",
        failed_to_create_tenant_group: "Failed to create tenant group.",
        existing_user: "Existing User",
        search_existing_users: "Search existing users...",
        search_existing_users_minimum_characters:
          "Type at least 3 characters to search existing users.",
        no_available_users_found: "No existing users available to add.",
        search_groups_or_roles: "Search groups or roles...",
        no_matching_groups_or_roles_found:
          "No groups or roles match your search.",
        tenant_role_reviewer: "Reviewer",
        tenant_role_submitter: "Submitter",
        close: "Close",
        cancel: "Cancel",
        add: "Add",
        save: "Save",
        remove: "Remove",
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

  const buildMembersPage = (
    allMembers: Array<{
      id: string;
      username: string;
      email: string | null;
      display_name: string | null;
      roles: string[];
      groups?: Array<{
        id: string;
        name: string;
      }>;
    }>,
    options?: {
      search?: string;
      offset?: number;
      limit?: number;
    },
  ) => {
    const normalizedSearch = options?.search?.trim().toLowerCase() ?? "";
    const offset = options?.offset ?? 0;
    const limit = options?.limit ?? 10;
    const filteredMembers = normalizedSearch
      ? allMembers.filter((member) =>
        [member.username, member.email ?? "", member.display_name ?? ""].some(
          (value) => value.toLowerCase().includes(normalizedSearch),
        ))
      : allMembers;
    const members = filteredMembers.slice(offset, offset + limit);
    return Promise.resolve({
      tenant_id: tenant.id,
      search: options?.search ?? "",
      offset,
      limit,
      has_more: offset + limit < filteredMembers.length,
      members,
    });
  };

  const buildAvailableUsersPage = (
    allUsers: Array<{
      id: string;
      username: string;
      email: string | null;
      display_name: string | null;
    }>,
    options?: {
      search?: string;
      offset?: number;
      limit?: number;
    },
  ) => {
    const normalizedSearch = options?.search?.trim().toLowerCase() ?? "";
    const offset = options?.offset ?? 0;
    const limit = options?.limit ?? 10;
    const filteredUsers = normalizedSearch
      ? allUsers.filter((user) =>
        [user.username, user.email ?? "", user.display_name ?? ""].some((value) =>
          value.toLowerCase().includes(normalizedSearch)
        ))
      : allUsers;
    const users = filteredUsers.slice(offset, offset + limit);
    return Promise.resolve({
      tenant_id: tenant.id,
      search: options?.search ?? "",
      offset,
      limit,
      has_more: offset + limit < filteredUsers.length,
      users,
    });
  };

  const buildGroupsPage = (
    allGroups: Array<{
      id: string;
      name: string;
      path: string | null;
      mapped_roles: string[];
      member_count: number;
      members: Array<{
        id: string;
        username: string;
        email: string | null;
        display_name: string | null;
      }>;
    }>,
    options?: {
      search?: string;
      offset?: number;
      limit?: number;
    },
  ) => {
    const normalizedSearch = options?.search?.trim().toLowerCase() ?? "";
    const offset = options?.offset ?? 0;
    const limit = options?.limit ?? 10;
    const filteredGroups = normalizedSearch
      ? allGroups.filter((group) =>
        [group.name, ...group.mapped_roles].some((value) =>
          value.toLowerCase().includes(normalizedSearch)
        ))
      : allGroups;
    const groups = filteredGroups.slice(offset, offset + limit);
    return Promise.resolve({
      tenant_id: tenant.id,
      search: options?.search ?? "",
      offset,
      limit,
      has_more: offset + limit < filteredGroups.length,
      groups,
    });
  };

  beforeEach(() => {
    vi.clearAllMocks();
    const tenantGroups = [
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
    ];
    mockGetTenantGroups.mockResolvedValue(tenantGroups);
    mockGetTenantGroupsPage.mockImplementation((_tenantId, options) =>
      buildGroupsPage(
        tenantGroups,
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));
    mockGetTenantMembers.mockImplementation((_tenantId, options) =>
      buildMembersPage(
        [
          {
            id: "member-1",
            username: "reviewer",
            email: "reviewer@example.com",
            display_name: "Reviewer User",
            roles: ["reviewer"],
            groups: [
              {
                id: "group-approvers",
                name: "Approvers",
              },
            ],
          },
          {
            id: "member-3",
            username: "submitter",
            email: "submitter@example.com",
            display_name: "Submitter User",
            roles: ["submitter"],
            groups: [
              {
                id: "group-submitters",
                name: "Submitters",
              },
            ],
          },
        ],
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));
    mockGetAvailableTenantUsers.mockImplementation((_tenantId, options) =>
      buildAvailableUsersPage(
        [
          {
            id: "member-2",
            username: "new.user",
            email: "new.user@example.com",
            display_name: "New User",
          },
        ],
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));
    mockAddTenantMember.mockResolvedValue({
      id: "member-2",
      username: "new.user",
      email: "new.user@example.com",
      display_name: "new.user",
      roles: ["reviewer"],
      groups: [
        {
          id: "group-approvers",
          name: "Approvers",
        },
      ],
    });
    mockCreateTenantGroup.mockResolvedValue({
      id: "group-manager",
      name: "Manager",
      path: "/Manager",
      mapped_roles: [],
      member_count: 0,
      members: [],
    });
    mockRenameTenantGroup.mockResolvedValue({
      id: "group-approvers",
      name: "QA Reviewers",
      path: "/QA Reviewers",
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
    });
    mockDeleteTenantGroup.mockResolvedValue("Approvers");
    mockAddTenantMemberToGroup.mockResolvedValue({
      id: "member-1",
      username: "reviewer",
      email: "reviewer@example.com",
      display_name: "Reviewer User",
      roles: ["reviewer"],
      groups: [
        {
          id: "group-approvers",
          name: "Approvers",
        },
        {
          id: "group-submitters",
          name: "Submitters",
        },
      ],
    });
    mockRemoveTenantMemberFromGroup.mockResolvedValue({
      id: "member-1",
      username: "reviewer",
      email: "reviewer@example.com",
      display_name: "Reviewer User",
      roles: [],
      groups: [],
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

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-member-add-button"));
    const addMemberDialog = await screen.findByRole("dialog", {
      name: "Add User to Tenant: Tenant One",
    });

    fireEvent.change(
      within(addMemberDialog).getByTestId(
        "tenant-member-existing-user-search-input",
      ),
      {
        target: { value: "new" },
      },
    );
    await waitFor(() =>
      expect(mockGetAvailableTenantUsers).toHaveBeenCalledWith("tenant-1", {
        search: "new",
        offset: 0,
        limit: 10,
      }),
    );
    expect(await within(addMemberDialog).findByText("New User")).toBeInTheDocument();
    fireEvent.click(
      within(addMemberDialog).getByTestId(
        "tenant-member-existing-user-option-new.user",
      ),
    );
    fireEvent.click(
      within(addMemberDialog).getByTestId("tenant-member-group-option-Approvers"),
    );
    fireEvent.click(
      within(addMemberDialog).getByTestId("tenant-member-submit-button"),
    );

    await waitFor(() =>
      expect(mockAddTenantMember).toHaveBeenCalledWith("tenant-1", {
        username: "new.user",
        group_names: ["Approvers"],
      }),
    );
  });

  it("loads the first member page on open and fetches page two only after next is clicked", async () => {
    mockGetTenantMembers.mockImplementation((_tenantId, options) =>
      buildMembersPage(
        Array.from({ length: 12 }, (_, index) => ({
          id: `member-${index + 1}`,
          username: `user-${index + 1}`,
          email: `user-${index + 1}@example.com`,
          display_name: `User ${index + 1}`,
          roles: index % 2 === 0 ? ["reviewer"] : ["submitter"],
        })),
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));

    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByTestId("tenant-member-table-container");
    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", {
        search: "",
        offset: 0,
        limit: 10,
      }),
    );
    expect(mockGetTenantMembers).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("User 1")).toBeInTheDocument();
    expect(screen.queryByText("User 11")).not.toBeInTheDocument();
    expect(screen.getByTestId("tenant-member-page-indicator")).toHaveTextContent("Page 1");

    fireEvent.click(screen.getByTestId("tenant-member-next-page-button"));

    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", {
        search: "",
        offset: 10,
        limit: 10,
      }),
    );
    expect(await screen.findByText("User 11")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-member-page-indicator")).toHaveTextContent("Page 2");
  });

  it("loads the first group page on open and fetches page two only after next is clicked", async () => {
    mockGetTenantGroupsPage.mockImplementation((_tenantId, options) =>
      buildGroupsPage(
        Array.from({ length: 12 }, (_, index) => ({
          id: `group-${index + 1}`,
          name: `Group ${index + 1}`,
          path: `/Group ${index + 1}`,
          mapped_roles: index % 2 === 0 ? ["reviewer"] : ["submitter"],
          member_count: 1,
          members: [
            {
              id: `member-${index + 1}`,
              username: `user-${index + 1}`,
              email: `user-${index + 1}@example.com`,
              display_name: `User ${index + 1}`,
            },
          ],
        })),
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));

    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await waitFor(() =>
      expect(mockGetTenantGroupsPage).toHaveBeenCalledWith("tenant-1", {
        search: "",
        offset: 0,
        limit: 10,
      }),
    );

    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));

    expect(await screen.findByTestId("tenant-group-table-container")).toBeInTheDocument();
    expect(await screen.findByText("Group 1")).toBeInTheDocument();
    expect(screen.queryByText("Group 11")).not.toBeInTheDocument();
    expect(screen.getByTestId("tenant-group-page-indicator")).toHaveTextContent("Page 1");

    fireEvent.click(screen.getByTestId("tenant-group-next-page-button"));

    await waitFor(() =>
      expect(mockGetTenantGroupsPage).toHaveBeenCalledWith("tenant-1", {
        search: "",
        offset: 10,
        limit: 10,
      }),
    );
    expect(await screen.findByText("Group 11")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-group-page-indicator")).toHaveTextContent("Page 2");
  });

  it("expands members and collapses groups by default, then toggles both sections", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByTestId("tenant-member-table-container");
    expect(screen.getByTestId("tenant-members-section-toggle")).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByTestId("tenant-groups-section-toggle")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByTestId("tenant-group-search-input")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));

    expect(await screen.findByTestId("tenant-group-search-input")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-groups-section-toggle")).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    fireEvent.click(screen.getByTestId("tenant-members-section-toggle"));

    await waitFor(() =>
      expect(
        screen.queryByTestId("tenant-member-table-container"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("tenant-members-section-toggle")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("renders each section action alongside its matching search input", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByTestId("tenant-member-table-container");
    expect(
      within(screen.getByTestId("tenant-members-toolbar")).getByTestId(
        "tenant-member-search-input",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("tenant-members-toolbar")).getByRole("button", {
        name: "Add Member",
      }),
    ).toHaveAttribute("data-testid", "tenant-member-add-button");

    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));

    expect(
      await screen.findByTestId("tenant-groups-toolbar"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("tenant-groups-toolbar")).getByTestId(
        "tenant-group-search-input",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("tenant-groups-toolbar")).getByTestId(
        "tenant-group-add-button",
      ),
    ).toBeInTheDocument();
  });

  it("loads the first available-user page on open and fetches page two only after next is clicked", async () => {
    mockGetAvailableTenantUsers.mockImplementation((_tenantId, options) =>
      buildAvailableUsersPage(
        Array.from({ length: 12 }, (_, index) => ({
          id: `available-user-${index + 1}`,
          username: `available-user-${index + 1}`,
          email: `available-user-${index + 1}@example.com`,
          display_name: `Available User ${index + 1}`,
        })),
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));

    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-member-add-button"));
    const addMemberDialog = await screen.findByRole("dialog", {
      name: "Add User to Tenant: Tenant One",
    });

    await waitFor(() =>
      expect(mockGetAvailableTenantUsers).toHaveBeenCalledWith("tenant-1", {
        search: "",
        offset: 0,
        limit: 10,
      }),
    );
    expect(mockGetAvailableTenantUsers).toHaveBeenCalledTimes(1);
    expect(
      await within(addMemberDialog).findByText("Available User 1"),
    ).toBeInTheDocument();
    expect(
      within(addMemberDialog).queryByText("Available User 11"),
    ).not.toBeInTheDocument();
    expect(
      within(addMemberDialog).getByTestId("tenant-available-user-page-indicator"),
    ).toHaveTextContent("Page 1");

    fireEvent.click(
      within(addMemberDialog).getByTestId(
        "tenant-available-user-next-page-button",
      ),
    );

    await waitFor(() =>
      expect(mockGetAvailableTenantUsers).toHaveBeenCalledWith("tenant-1", {
        search: "",
        offset: 10,
        limit: 10,
      }),
    );
    expect(
      await within(addMemberDialog).findByText("Available User 11"),
    ).toBeInTheDocument();
    expect(
      within(addMemberDialog).getByTestId("tenant-available-user-page-indicator"),
    ).toHaveTextContent("Page 2");
  });

  it("does not render the group path below the group name", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    expect(screen.queryByText("/Approvers")).not.toBeInTheDocument();
  });

  it("manages tenant group membership from the member actions dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByTestId("tenant-member-search-input");
    fireEvent.change(screen.getByTestId("tenant-member-search-input"), {
      target: { value: "rev" },
    });
    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", {
        search: "rev",
        offset: 0,
        limit: 10,
      }),
    );
    await screen.findByText("Reviewer User");
    fireEvent.click(screen.getByTestId("tenant-member-manage-groups-button-reviewer"));
    await screen.findByTestId("tenant-member-groups-dialog");
    fireEvent.click(
      screen.getByTestId(
        "tenant-member-groups-dialog-checkbox-reviewer-Submitters",
      ),
    );

    await waitFor(() =>
      expect(mockAddTenantMemberToGroup).toHaveBeenCalledWith(
        "tenant-1",
        "reviewer",
        "Submitters",
      ),
    );
  });

  it("removes a tenant member from all assigned groups", async () => {
    const tenantGroups = [
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
      {
        id: "group-submitters",
        name: "Submitters",
        path: "/Submitters",
        mapped_roles: ["submitter"],
        member_count: 2,
        members: [
          {
            id: "member-1",
            username: "reviewer",
            email: "reviewer@example.com",
            display_name: "Reviewer User",
          },
          {
            id: "member-3",
            username: "submitter",
            email: "submitter@example.com",
            display_name: "Submitter User",
          },
        ],
      },
    ];
    mockGetTenantGroups.mockResolvedValue(tenantGroups);
    mockGetTenantGroupsPage.mockImplementation((_tenantId, options) =>
      buildGroupsPage(
        tenantGroups,
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));
    mockGetTenantMembers.mockImplementation((_tenantId, options) =>
      buildMembersPage(
        [
          {
            id: "member-1",
            username: "reviewer",
            email: "reviewer@example.com",
            display_name: "Reviewer User",
            roles: ["reviewer", "submitter"],
            groups: [
              { id: "group-approvers", name: "Approvers" },
              { id: "group-submitters", name: "Submitters" },
            ],
          },
          {
            id: "member-3",
            username: "submitter",
            email: "submitter@example.com",
            display_name: "Submitter User",
            roles: ["submitter"],
            groups: [
              { id: "group-submitters", name: "Submitters" },
            ],
          },
        ],
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));

    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByTestId("tenant-member-table-container");
    fireEvent.click(screen.getByTestId("tenant-member-remove-button-reviewer"));
    await screen.findByTestId("tenant-member-remove-dialog");
    fireEvent.click(screen.getByTestId("tenant-member-remove-confirm-button"));

    await waitFor(() =>
      expect(mockRemoveTenantMemberFromGroup).toHaveBeenNthCalledWith(
        1,
        "tenant-1",
        "reviewer",
        "Approvers",
      ),
    );
    await waitFor(() =>
      expect(mockRemoveTenantMemberFromGroup).toHaveBeenNthCalledWith(
        2,
        "tenant-1",
        "reviewer",
        "Submitters",
      ),
    );
  });

  it("renders effective roles for each tenant member", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByTestId("tenant-member-table-container");
    expect(
      screen.getByTestId("tenant-member-role-chip-reviewer-reviewer"),
    ).toHaveTextContent("Reviewer");
    expect(
      screen.getByTestId("tenant-member-role-chip-submitter-submitter"),
    ).toHaveTextContent("Submitter");
  });

  it("manages granted roles from the group actions dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    fireEvent.click(screen.getByTestId("tenant-group-manage-roles-button-Approvers"));
    await screen.findByTestId("tenant-group-roles-dialog");
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

  it("renames a tenant group from the group actions dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    fireEvent.click(screen.getByTestId("tenant-group-rename-button-Approvers"));
    await screen.findByTestId("tenant-group-rename-dialog");
    fireEvent.change(screen.getByTestId("tenant-group-rename-input"), {
      target: { value: "QA Reviewers" },
    });
    await waitFor(() =>
      expect(screen.getByTestId("tenant-group-rename-submit-button")).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId("tenant-group-rename-submit-button"));

    await waitFor(() =>
      expect(mockRenameTenantGroup).toHaveBeenCalledWith("tenant-1", "Approvers", {
        name: "QA Reviewers",
      }),
    );
  });

  it("removes a tenant group from the group actions dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    fireEvent.click(screen.getByTestId("tenant-group-remove-button-Approvers"));
    await screen.findByTestId("tenant-group-remove-dialog");
    fireEvent.click(screen.getByTestId("tenant-group-remove-confirm-button"));

    await waitFor(() =>
      expect(mockDeleteTenantGroup).toHaveBeenCalledWith("tenant-1", "Approvers"),
    );
  });

  it("renders the submitter granted role when returned by the backend", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    expect(await screen.findAllByText("Submitter")).not.toHaveLength(0);
    expect(screen.getAllByText("Submitters").length).toBeGreaterThan(0);
  });

  it("creates a tenant group from the dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    fireEvent.click(screen.getByTestId("tenant-group-add-button"));
    await screen.findByTestId("tenant-group-name-input");
    fireEvent.change(screen.getByTestId("tenant-group-name-input"), {
      target: { value: "Manager" },
    });
    await waitFor(() =>
      expect(screen.getByTestId("tenant-group-submit-button")).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId("tenant-group-submit-button"));

    await waitFor(() =>
      expect(mockCreateTenantGroup).toHaveBeenCalledWith("tenant-1", {
        name: "Manager",
      }),
    );
  });

  it("blocks invalid special characters in the create-group dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    fireEvent.click(screen.getByTestId("tenant-group-add-button"));
    fireEvent.change(screen.getByTestId("tenant-group-name-input"), {
      target: { value: "Bad %#@! group" },
    });

    expect(
      screen.getByText(
        "Group name can only contain letters, numbers, spaces, hyphens, and underscores, and must start and end with a letter or number",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("tenant-group-submit-button")).toBeDisabled();
    expect(mockCreateTenantGroup).not.toHaveBeenCalled();
  });

  it("normalizes group-name whitespace before submit", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    fireEvent.click(screen.getByTestId("tenant-group-add-button"));
    await screen.findByTestId("tenant-group-name-input");
    fireEvent.change(screen.getByTestId("tenant-group-name-input"), {
      target: { value: "  Manager   Team  " },
    });
    fireEvent.blur(screen.getByTestId("tenant-group-name-input"));
    await waitFor(() =>
      expect(screen.getByTestId("tenant-group-submit-button")).toBeEnabled(),
    );
    fireEvent.click(screen.getByTestId("tenant-group-submit-button"));

    await waitFor(() =>
      expect(mockCreateTenantGroup).toHaveBeenCalledWith("tenant-1", {
        name: "Manager Team",
      }),
    );
  });

  it("renders long group names in fixed-width truncated cells and tooltips across dialogs", async () => {
    const longGroupName =
      "This is a very long tenant group name that should not stretch the table layout";
    const tenantGroups = [
      {
        id: "group-long",
        name: longGroupName,
        path: `/${longGroupName}`,
        mapped_roles: [],
        member_count: 0,
        members: [],
      },
    ];
    mockGetTenantGroups.mockResolvedValue(tenantGroups);
    mockGetTenantGroupsPage.mockImplementation((_tenantId, options) =>
      buildGroupsPage(
        tenantGroups,
        options as { search?: string; offset?: number; limit?: number } | undefined,
      ));

    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findByTestId("tenant-member-search-input");
    fireEvent.change(screen.getByTestId("tenant-member-search-input"), {
      target: { value: "rev" },
    });
    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", {
        search: "rev",
        offset: 0,
        limit: 10,
      }),
    );
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    const groupNameCell = await screen.findByTestId(
      "tenant-group-name-cell-group-long",
    );
    fireEvent.click(screen.getByTestId("tenant-member-add-button"));
    const addMemberGroupLabel = await screen.findByTestId(
      "tenant-member-group-label-group-long",
    );

    expect(groupNameCell).toHaveStyle({
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
    });
    expect(addMemberGroupLabel).toHaveStyle({
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
    });

    fireEvent.mouseOver(addMemberGroupLabel);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(longGroupName);
  });

  it("filters main groups by group name or mapped role", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-groups-section-toggle"));
    await screen.findByTestId("tenant-group-search-input");
    fireEvent.change(screen.getByTestId("tenant-group-search-input"), {
      target: { value: "reviewer" },
    });

    await waitFor(() =>
      expect(mockGetTenantGroupsPage).toHaveBeenCalledWith("tenant-1", {
        search: "reviewer",
        offset: 0,
        limit: 10,
      }),
    );
    expect(
      await screen.findByTestId("tenant-group-name-cell-group-approvers"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByTestId("tenant-group-name-cell-group-submitters"),
      ).not.toBeInTheDocument(),
    );
  });

  it("filters add-member groups by group name or mapped role", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-member-add-button"));
    const addMemberDialog = await screen.findByRole("dialog", {
      name: "Add User to Tenant: Tenant One",
    });

    expect(
      within(addMemberDialog).getByTestId(
        "tenant-member-group-label-group-approvers",
      ),
    ).toBeInTheDocument();
    expect(
      within(addMemberDialog).getByTestId(
        "tenant-member-group-label-group-submitters",
      ),
    ).toBeInTheDocument();

    fireEvent.change(
      within(addMemberDialog).getByTestId("tenant-member-group-search-input"),
      {
        target: { value: "reviewer" },
      },
    );

    expect(
      within(addMemberDialog).getByTestId(
        "tenant-member-group-label-group-approvers",
      ),
    ).toBeInTheDocument();
    expect(
      within(addMemberDialog).queryByTestId(
        "tenant-member-group-label-group-submitters",
      ),
    ).not.toBeInTheDocument();

    fireEvent.change(
      within(addMemberDialog).getByTestId("tenant-member-group-search-input"),
      {
        target: { value: "does-not-match" },
      },
    );

    expect(
      within(addMemberDialog).getByText("No groups or roles match your search."),
    ).toBeInTheDocument();
  });
});

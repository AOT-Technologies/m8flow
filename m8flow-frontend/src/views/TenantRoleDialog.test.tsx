import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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

vi.mock("../services/TenantService", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/TenantService")>();
  return {
    ...actual,
    default: {
      ...actual.default,
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
  };
});

vi.mock("react-i18next", () => ({
  initReactI18next: {
    type: "3rdParty",
    init: () => undefined,
  },
  useTranslation: () => ({
    t: (key: string) => {
      const messages: Record<string, string> = {
        manage_tenant_groups: "Manage Tenant Groups",
        tenant_group_management_description:
          "Add existing members and manage groups and roles associated with this tenant.",
        search_organization_members: "Search tenant members...",
        search_tenant_members_minimum_characters:
          "Type at least 3 characters to search tenant members.",
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
          "Add an existing user to this tenant, then assign groups.",
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
      expect(mockGetAvailableTenantUsers).toHaveBeenCalledWith("tenant-1", "new"),
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

  it("loads main tenant members only after three characters are typed", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    expect(mockGetTenantMembers).not.toHaveBeenCalled();
    expect(
      screen.getByText("Type at least 3 characters to search tenant members."),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("tenant-member-search-input"), {
      target: { value: "re" },
    });

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 250));
    });
    expect(mockGetTenantMembers).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId("tenant-member-search-input"), {
      target: { value: "rev" },
    });

    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", "rev"),
    );
    expect(await screen.findByText("Reviewer User")).toBeInTheDocument();
  });

  it("waits for at least three characters before loading existing users", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    fireEvent.click(screen.getByTestId("tenant-member-add-button"));
    const addMemberDialog = await screen.findByRole("dialog", {
      name: "Add User to Tenant: Tenant One",
    });

    expect(mockGetAvailableTenantUsers).not.toHaveBeenCalled();
    expect(
      within(addMemberDialog).getByText(
        "Type at least 3 characters to search existing users.",
      ),
    ).toBeInTheDocument();

    fireEvent.change(
      within(addMemberDialog).getByTestId(
        "tenant-member-existing-user-search-input",
      ),
      {
        target: { value: "ne" },
      },
    );

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 250));
    });
    expect(mockGetAvailableTenantUsers).not.toHaveBeenCalled();

    fireEvent.change(
      within(addMemberDialog).getByTestId(
        "tenant-member-existing-user-search-input",
      ),
      {
        target: { value: "new" },
      },
    );

    await waitFor(() =>
      expect(mockGetAvailableTenantUsers).toHaveBeenCalledWith("tenant-1", "new"),
    );
    expect(await within(addMemberDialog).findByText("New User")).toBeInTheDocument();
  });

  it("does not render the group path below the group name", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
    expect(screen.queryByText("/Approvers")).not.toBeInTheDocument();
  });

  it("toggles tenant group membership from the member matrix", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    fireEvent.change(screen.getByTestId("tenant-member-search-input"), {
      target: { value: "rev" },
    });
    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", "rev"),
    );
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

    await screen.findAllByText("Approvers");
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

    await screen.findAllByText("Approvers");
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

  it("blocks invalid special characters in the create-group dialog", async () => {
    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    await screen.findAllByText("Approvers");
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
    fireEvent.click(screen.getByTestId("tenant-group-add-button"));
    fireEvent.change(screen.getByTestId("tenant-group-name-input"), {
      target: { value: "  Manager   Team  " },
    });
    fireEvent.blur(screen.getByTestId("tenant-group-name-input"));
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
    mockGetTenantGroups.mockResolvedValue([
      {
        id: "group-long",
        name: longGroupName,
        path: `/${longGroupName}`,
        mapped_roles: [],
        member_count: 0,
        members: [],
      },
    ]);

    render(<TenantRoleDialog open tenant={tenant} onClose={vi.fn()} />);

    fireEvent.change(screen.getByTestId("tenant-member-search-input"), {
      target: { value: "rev" },
    });
    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", "rev"),
    );
    const headerLabel = await screen.findByTestId(
      "tenant-members-group-header-group-long",
    );
    const groupNameCell = await screen.findByTestId(
      "tenant-group-name-cell-group-long",
    );
    fireEvent.click(screen.getByTestId("tenant-member-add-button"));
    const addMemberGroupLabel = await screen.findByTestId(
      "tenant-member-group-label-group-long",
    );

    expect(headerLabel).toHaveStyle({
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
    });
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
    fireEvent.change(screen.getByTestId("tenant-member-search-input"), {
      target: { value: "rev" },
    });
    await waitFor(() =>
      expect(mockGetTenantMembers).toHaveBeenCalledWith("tenant-1", "rev"),
    );
    await screen.findByText("Reviewer User");
    expect(
      screen.getByTestId("tenant-members-group-header-group-approvers"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("tenant-members-group-header-group-submitters"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("tenant-group-search-input"), {
      target: { value: "reviewer" },
    });

    expect(
      screen.getByTestId("tenant-group-name-cell-group-approvers"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("tenant-group-name-cell-group-submitters"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("tenant-members-group-header-group-approvers"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("tenant-members-group-header-group-submitters"),
    ).not.toBeInTheDocument();
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

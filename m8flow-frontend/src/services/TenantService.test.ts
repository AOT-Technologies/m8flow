import { beforeEach, describe, expect, it, vi } from "vitest";
import HttpService from "@spiffworkflow-frontend/services/HttpService";
import TenantService, {
  normalizeTenantGroupName,
  validateTenantGroupName,
} from "./TenantService";

vi.mock("@spiffworkflow-frontend/services/HttpService", () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

describe("TenantService group name validation", () => {
  beforeEach(() => {
    vi.mocked(HttpService.makeCallToBackend).mockReset();
  });

  it("collapses repeated whitespace when normalizing group names", () => {
    expect(normalizeTenantGroupName("  QA   Reviewers  ")).toBe("QA Reviewers");
  });

  it("rejects invalid special characters before sending the create-group request", async () => {
    await expect(
      TenantService.createTenantGroup("tenant-1", {
        name: "Invalid %#@! group",
      }),
    ).rejects.toThrow(
      "Group name can only contain letters, numbers, spaces, hyphens, and underscores, and must start and end with a letter or number",
    );

    expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
  });

  it("normalizes whitespace before sending the create-group request", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      options.successCallback?.({
        tenant_id: "tenant-1",
        group: {
          id: "group-1",
          name: "QA Reviewers",
          path: "/QA Reviewers",
          mapped_roles: [],
          member_count: 0,
          members: [],
        },
      });
    });

    await TenantService.createTenantGroup("tenant-1", {
      name: "  QA   Reviewers  ",
    });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/groups",
        httpMethod: "POST",
        postBody: { name: "QA Reviewers" },
      }),
    );
  });

  it("returns a validation message for overly long group names", () => {
    expect(validateTenantGroupName("a".repeat(65))).toBe(
      "Group name must be 64 characters or fewer",
    );
  });

  it("normalizes whitespace before sending the rename-group request", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      options.successCallback?.({
        tenant_id: "tenant-1",
        previous_group_name: "Approvers",
        group: {
          id: "group-1",
          name: "QA Reviewers",
          path: "/QA Reviewers",
          mapped_roles: ["reviewer"],
          member_count: 1,
          members: [],
        },
      });
    });

    await TenantService.renameTenantGroup("tenant-1", "Approvers", {
      name: "  QA   Reviewers  ",
    });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/groups/Approvers",
        httpMethod: "PUT",
        postBody: { name: "QA Reviewers" },
      }),
    );
  });

  it("sends the delete-group request to the tenant group endpoint", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      options.successCallback?.({
        tenant_id: "tenant-1",
        group_name: "QA Reviewers",
      });
    });

    await expect(
      TenantService.deleteTenantGroup("tenant-1", "QA Reviewers"),
    ).resolves.toBe("QA Reviewers");

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/groups/QA%20Reviewers",
        httpMethod: "DELETE",
      }),
    );
  });

  it("requests one page of tenant groups with offset and limit", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      options.successCallback?.({
        tenant_id: "tenant-1",
        search: "review",
        offset: 10,
        limit: 10,
        has_more: true,
        groups: [],
      });
    });

    await expect(
      TenantService.getTenantGroupsPage("tenant-1", {
        search: "review",
        offset: 10,
        limit: 10,
      }),
    ).resolves.toEqual({
      tenant_id: "tenant-1",
      search: "review",
      offset: 10,
      limit: 10,
      has_more: true,
      groups: [],
    });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/groups?search=review&offset=10&limit=10",
        httpMethod: "GET",
      }),
    );
  });

  it("normalizes missing member groups to an empty array", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      options.successCallback?.({
        tenant_id: "tenant-1",
        search: "",
        offset: 0,
        limit: 10,
        has_more: false,
        members: [
          {
            id: "member-1",
            username: "reviewer",
            email: "reviewer@example.com",
            display_name: "Reviewer User",
            roles: ["reviewer"],
          },
        ],
      });
    });

    await expect(
      TenantService.getTenantMembersPage("tenant-1", {
        offset: 0,
        limit: 10,
      }),
    ).resolves.toEqual({
      tenant_id: "tenant-1",
      search: "",
      offset: 0,
      limit: 10,
      has_more: false,
      members: [
        {
          id: "member-1",
          username: "reviewer",
          email: "reviewer@example.com",
          display_name: "Reviewer User",
          roles: ["reviewer"],
          groups: [],
        },
      ],
    });
  });

  it("aggregates tenant groups across pages", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      if (options.path.includes("offset=0")) {
        options.successCallback?.({
          tenant_id: "tenant-1",
          search: "",
          offset: 0,
          limit: 100,
          has_more: true,
          groups: [
            {
              id: "group-1",
              name: "Approvers",
              path: "/Approvers",
              mapped_roles: ["reviewer"],
              member_count: 1,
              members: [],
            },
          ],
        });
        return;
      }

      options.successCallback?.({
        tenant_id: "tenant-1",
        search: "",
        offset: 1,
        limit: 100,
        has_more: false,
        groups: [
          {
            id: "group-2",
            name: "Submitters",
            path: "/Submitters",
            mapped_roles: ["submitter"],
            member_count: 1,
            members: [],
          },
        ],
      });
    });

    await expect(TenantService.getTenantGroups("tenant-1")).resolves.toEqual([
      {
        id: "group-1",
        name: "Approvers",
        path: "/Approvers",
        mapped_roles: ["reviewer"],
        member_count: 1,
        members: [],
      },
      {
        id: "group-2",
        name: "Submitters",
        path: "/Submitters",
        mapped_roles: ["submitter"],
        member_count: 1,
        members: [],
      },
    ]);
  });

  it("rejects stale tenant group pagination responses", async () => {
    let callCount = 0;
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      callCount += 1;
      if (callCount === 1) {
        options.successCallback?.({
          tenant_id: "tenant-1",
          search: "",
          offset: 0,
          limit: 100,
          has_more: true,
          groups: [
            {
              id: "group-1",
              name: "Approvers",
              path: "/Approvers",
              mapped_roles: ["reviewer"],
              member_count: 1,
              members: [],
            },
          ],
        });
        return;
      }

      options.successCallback?.({
        tenant_id: "tenant-1",
        search: "",
        offset: 0,
        limit: 100,
        has_more: true,
        groups: [
          {
            id: "group-1",
            name: "Approvers",
            path: "/Approvers",
            mapped_roles: ["reviewer"],
            member_count: 1,
            members: [],
          },
        ],
      });
    });

    await expect(TenantService.getTenantGroups("tenant-1")).rejects.toThrow(
      "Tenant group pagination returned a stale page.",
    );
    expect(callCount).toBe(2);
  });
});

describe("TenantService invitations", () => {
  beforeEach(() => {
    vi.mocked(HttpService.makeCallToBackend).mockReset();
  });

  const mockSuccess = (payload: unknown) => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((options: any) => {
      options.successCallback?.(payload);
    });
  };

  it("rejects creating an invitation with an empty email before any HTTP call", async () => {
    await expect(
      TenantService.createInvitation("tenant-1", { email: "  ", roles: ["editor"] }),
    ).rejects.toThrow("Email cannot be empty");
    expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
  });

  it("rejects creating an invitation with no roles before any HTTP call", async () => {
    await expect(
      TenantService.createInvitation("tenant-1", { email: "user@example.com", roles: [] }),
    ).rejects.toThrow("At least one role is required");
    expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
  });

  it("posts the create-invitation request and includes validity_days when provided", async () => {
    mockSuccess({
      tenant_id: "tenant-1",
      invitation: { id: "inv-1", email: "user@example.com", status: "PENDING" },
    });

    await expect(
      TenantService.createInvitation("tenant-1", {
        email: "  user@example.com  ",
        roles: ["editor", "viewer"],
        validity_days: 7,
      }),
    ).resolves.toEqual({ id: "inv-1", email: "user@example.com", status: "PENDING" });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/invitations",
        httpMethod: "POST",
        postBody: {
          email: "user@example.com",
          roles: ["editor", "viewer"],
          validity_days: 7,
        },
      }),
    );
  });

  it("omits validity_days from the create-invitation body when not provided", async () => {
    mockSuccess({ tenant_id: "tenant-1", invitation: { id: "inv-1" } });

    await TenantService.createInvitation("tenant-1", {
      email: "user@example.com",
      roles: ["editor"],
    });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        postBody: { email: "user@example.com", roles: ["editor"] },
      }),
    );
  });

  it("builds the list-invitations query with status, offset and clamped limit", async () => {
    mockSuccess({
      tenant_id: "tenant-1",
      results: [{ id: "inv-1", email: "user@example.com", status: "PENDING" }],
      total: 1,
      offset: 0,
      limit: 50,
    });

    await expect(
      TenantService.listInvitations("tenant-1", { status: "PENDING", offset: -5, limit: 0 }),
    ).resolves.toEqual({
      results: [{ id: "inv-1", email: "user@example.com", status: "PENDING" }],
      total: 1,
      offset: 0,
      limit: 50,
    });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/invitations?status=PENDING&offset=0&limit=1",
        httpMethod: "GET",
      }),
    );
  });

  it("uses default offset and limit for list-invitations when options are omitted", async () => {
    mockSuccess({ tenant_id: "tenant-1", results: [], total: 0, offset: 0, limit: 50 });

    await TenantService.listInvitations("tenant-1");

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/invitations?offset=0&limit=50",
      }),
    );
  });

  it("posts the resend-invitation request to the resend endpoint", async () => {
    mockSuccess({ tenant_id: "tenant-1", invitation: { id: "inv-1", status: "PENDING" } });

    await expect(
      TenantService.resendInvitation("tenant-1", "inv-1"),
    ).resolves.toEqual({ id: "inv-1", status: "PENDING" });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/invitations/inv-1/resend",
        httpMethod: "POST",
      }),
    );
  });

  it("deletes the invitation when revoking", async () => {
    mockSuccess({ tenant_id: "tenant-1", invitation: { id: "inv-1", status: "REVOKED" } });

    await expect(
      TenantService.revokeInvitation("tenant-1", "inv-1"),
    ).resolves.toEqual({ id: "inv-1", status: "REVOKED" });

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/tenants/tenant-1/invitations/inv-1",
        httpMethod: "DELETE",
      }),
    );
  });

  it("validates an invitation token with a URL-encoded query parameter", async () => {
    const validation = {
      email: "user@example.com",
      tenant_id: "tenant-1",
      tenant_name: "Acme Corp",
      roles: ["editor"],
      expires_at_in_seconds: 123,
    };
    mockSuccess(validation);

    await expect(
      TenantService.validateInvitation("raw token/with+chars"),
    ).resolves.toEqual(validation);

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/invitations/validate?token=raw%20token%2Fwith%2Bchars",
        httpMethod: "GET",
      }),
    );
  });

  it("posts the token and password when accepting an invitation", async () => {
    const result = {
      email: "user@example.com",
      tenant_id: "tenant-1",
      tenant_name: "Acme Corp",
      roles: ["editor"],
      smtp_configured: false,
    };
    mockSuccess(result);

    await expect(
      TenantService.acceptInvitation("raw-token", "password123"),
    ).resolves.toEqual(result);

    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/v1.0/m8flow/invitations/accept",
        httpMethod: "POST",
        postBody: { token: "raw-token", password: "password123" },
      }),
    );
  });
});

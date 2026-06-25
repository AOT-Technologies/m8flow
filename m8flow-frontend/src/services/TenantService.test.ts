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

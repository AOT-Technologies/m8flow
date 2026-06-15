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
});

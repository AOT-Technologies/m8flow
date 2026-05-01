import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantPage from "./TenantPage";

const mockUseTenants = vi.fn();
const mockUsePermissionFetcher = vi.fn();
const mockCreateTenant = vi.fn();

vi.mock("../hooks/useTenants", () => ({
  useTenants: () => mockUseTenants(),
}));

vi.mock("@spiffworkflow-frontend/hooks/PermissionService", () => ({
  usePermissionFetcher: () => mockUsePermissionFetcher(),
}));

vi.mock("../services/TenantService", () => ({
  default: {
    createTenant: (...args: unknown[]) => mockCreateTenant(...args),
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
});

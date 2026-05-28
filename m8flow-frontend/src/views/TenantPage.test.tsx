import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantPage from "./TenantPage";

// Mock react-i18next – the TenantModal uses t("realm_slug"), t("display_name"), etc.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number; defaultValue?: string }) => {
      const map: Record<string, string> = {
        realm_slug: "Realm Slug",
        display_name: "Display Name",
        tenant_management: "Tenant Management",
        add_tenant: "Add Tenant",
        tenant_slug_cannot_be_empty: "Tenant slug cannot be empty",
        tenant_display_name_cannot_be_empty:
          "Tenant display name cannot be empty",
        tenant_slug_invalid_pattern:
          "Tenant slug can only contain letters, numbers, hyphens, and underscores",
        tenant_display_name_max_length:
          "Tenant display name must be 50 characters or fewer",
        tenant_slug_already_exists: "Tenant slug already exists",
        tenant_created_successfully: "Tenant created successfully.",
        tenant_updated_successfully: "Tenant updated successfully.",
        cancel: "Cancel",
        create: "Create",
        save: "Save",
        delete: "Delete",
        edit_tenant: "Edit Tenant",
        delete_tenant: "Delete Tenant",
        search_by: "Search By",
        name: "Name",
      };
      return map[key] ?? opts?.defaultValue ?? key;
    },
  }),
}));

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
      realm: "it",
      displayName: "Information Technology",
      keycloak_realm_id: "tenant-uuid",
      id: "tenant-uuid",
    });

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-add-button"));

    fireEvent.change(screen.getByLabelText("Realm Slug"), {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByLabelText("Display Name"), {
      target: { value: "Information Technology" },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    await waitFor(() => {
      expect(mockCreateTenant).toHaveBeenCalledWith({
        realm_id: "it-team_1",
        display_name: "Information Technology",
      });
    });

    await waitFor(() => {
      expect(refetch).toHaveBeenCalled();
    });

    expect(await screen.findByText("Tenant created successfully.")).toBeInTheDocument();
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

    expect(await screen.findByText("Tenant slug cannot be empty")).toBeInTheDocument();
    expect(await screen.findByText("Tenant display name cannot be empty")).toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText("Realm Slug"), {
      target: { value: "it team" },
    });
    fireEvent.change(screen.getByLabelText("Display Name"), {
      target: { value: "A".repeat(51) },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText(
        "Tenant slug can only contain letters, numbers, hyphens, and underscores",
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Tenant display name must be 50 characters or fewer"),
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
      detail: "Realm already exists or conflict",
    });

    render(<TenantPage />);

    fireEvent.click(screen.getByTestId("tenant-add-button"));
    fireEvent.change(screen.getByLabelText("Realm Slug"), {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByLabelText("Display Name"), {
      target: { value: "Information Technology" },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(await screen.findByText("Tenant slug already exists")).toBeInTheDocument();
  });
});

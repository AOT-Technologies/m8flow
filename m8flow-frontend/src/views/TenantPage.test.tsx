import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TenantPage from "./TenantPage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (options && "defaultValue" in options && typeof options.defaultValue === "string") {
        return options.defaultValue;
      }
      return key;
    },
  }),
}));

vi.mock("@mui/icons-material", () => ({
  Search: () => <svg data-testid="icon-search" />,
  Edit: () => <svg data-testid="icon-edit" />,
  Clear: () => <svg data-testid="icon-clear" />,
  Add: () => <svg data-testid="icon-add" />,
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
    await screen.findByTestId("tenant-modal-dialog");

    fireEvent.change(screen.getByTestId("tenant-realm-id-input").querySelector("input")!, {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByTestId("tenant-display-name-input").querySelector("input")!, {
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

    expect(await screen.findByText("tenant_created_successfully")).toBeInTheDocument();
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
    await screen.findByTestId("tenant-modal-dialog");
    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(await screen.findByText("tenant_slug_cannot_be_empty")).toBeInTheDocument();
    expect(await screen.findByText("tenant_display_name_cannot_be_empty")).toBeInTheDocument();
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
    await screen.findByTestId("tenant-modal-dialog");

    fireEvent.change(screen.getByTestId("tenant-realm-id-input").querySelector("input")!, {
      target: { value: "it team" },
    });
    fireEvent.change(screen.getByTestId("tenant-display-name-input").querySelector("input")!, {
      target: { value: "A".repeat(51) },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(
      await screen.findByText(
        "tenant_slug_invalid_pattern",
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("tenant_display_name_max_length"),
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
    await screen.findByTestId("tenant-modal-dialog");
    fireEvent.change(screen.getByTestId("tenant-realm-id-input").querySelector("input")!, {
      target: { value: "it-team_1" },
    });
    fireEvent.change(screen.getByTestId("tenant-display-name-input").querySelector("input")!, {
      target: { value: "Information Technology" },
    });

    fireEvent.click(screen.getByTestId("tenant-modal-submit-button"));

    expect(await screen.findByText("tenant_slug_already_exists")).toBeInTheDocument();
  });
});

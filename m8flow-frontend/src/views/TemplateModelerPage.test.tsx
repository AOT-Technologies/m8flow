import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import type React from "react";
import TemplateModelerPage from "./TemplateModelerPage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key,
  }),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useParams: vi.fn(),
    useNavigate: vi.fn(() => vi.fn()),
  };
});

vi.mock("../services/HttpService", () => ({
  default: {
    HttpMethods: { GET: "GET", PUT: "PUT" },
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock("../services/TemplateService", () => ({
  default: {
    exportTemplate: vi.fn(),
    updateTemplate: vi.fn(),
    getAllVersions: vi.fn(() => Promise.resolve([])),
    deleteTemplate: vi.fn(() => Promise.resolve()),
  },
}));

vi.mock("../services/UserService", () => ({
  default: {
    getUserName: vi.fn(() => "tester"),
    getPreferredUsername: vi.fn(() => "tester"),
  },
}));

vi.mock("@spiffworkflow-frontend/hooks/PermissionService", () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: () => true },
    permissionsLoaded: true,
  })),
}));

vi.mock("@spiffworkflow-frontend/components/ProcessBreadcrumb", () => ({
  default: () => <div data-testid="breadcrumb">Breadcrumb</div>,
}));

vi.mock("@spiffworkflow-frontend/services/DateAndTimeService", () => ({
  default: {
    convertSecondsToFormattedDateTime: vi.fn(() => "Jan 1, 2024"),
  },
}));

vi.mock("../components/TemplateFileList", () => ({
  default: () => <div data-testid="template-file-list">File list</div>,
}));

vi.mock("../components/CreateProcessModelFromTemplateModal", () => ({
  default: () => null,
}));

import { useParams } from "react-router-dom";
import HttpService from "../services/HttpService";
import TemplateService from "../services/TemplateService";
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";

const theme = createTheme();

function templatePayload(overrides: Record<string, unknown> = {}) {
  return {
    id: 5,
    templateKey: "test-key",
    name: overrides.name ?? "Test Template",
    version: "V1",
    visibility: overrides.visibility ?? "TENANT",
    createdBy: overrides.createdBy ?? "tester",
    files: [],
    isPublished: overrides.isPublished ?? false,
    createdAt: "2024-01-01T00:00:00.000Z",
    updatedAt: "2024-01-01T00:00:00.000Z",
    ...overrides,
  };
}

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>{ui}</MemoryRouter>
    </ThemeProvider>
  );
}

function visibilityCombobox() {
  return screen.getByRole("combobox");
}

describe("TemplateModelerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useParams).mockReturnValue({ templateId: "5" });
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload() as never);
    });
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: { can: () => true } as never,
      permissionsLoaded: true,
    });
  });

  it("renders template name and shows Delete button for draft owned by current user", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Template")).toBeInTheDocument();
    });

    expect(screen.getByTestId("template-delete-button")).toBeInTheDocument();
    expect(screen.getByTestId("template-delete-button")).toBeEnabled();
  });

  it("shows Publish button when template is not published", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByTestId("template-publish-button")).toBeInTheDocument();
    });
  });

  it("does not show Publish button when template is published", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText("Test Template")).toBeInTheDocument();
    });

    expect(screen.queryByTestId("template-publish-button")).not.toBeInTheDocument();
  });

  it("disables Create Process Model button when template version is draft", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    const createButton = await screen.findByTestId("template-create-process-model-button");
    expect(createButton).toBeDisabled();
  });

  it("enables Create Process Model button when template version is published", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    const createButton = await screen.findByTestId("template-create-process-model-button");
    expect(createButton).toBeEnabled();
  });

  it("disables Delete for published template when user lacks admin permission", async () => {
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: {
        can: (_method: string, uri: string) => {
          if (uri === "/m8flow/admin/templates") return false;
          return true;
        },
      } as never,
      permissionsLoaded: true,
    });
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    const deleteButton = await screen.findByTestId("template-delete-button");
    expect(deleteButton).toBeDisabled();
  });

  it("enables Delete for published template when user has admin permission", async () => {
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: { can: () => true } as never,
      permissionsLoaded: true,
    });
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    const deleteButton = await screen.findByTestId("template-delete-button");
    expect(deleteButton).toBeEnabled();
  });

  it("shows visibility dropdown for draft template when user has edit permission", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "TENANT" }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByTestId("template-visibility-select")).toBeInTheDocument();
    });

    expect(screen.queryByText("visibility: TENANT")).not.toBeInTheDocument();
  });

  it("shows read-only visibility chip for published template", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true, visibility: "TENANT" }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText("visibility: TENANT")).toBeInTheDocument();
    });

    expect(screen.queryByTestId("template-visibility-select")).not.toBeInTheDocument();
  });

  it("shows read-only visibility chip when user lacks edit permission", async () => {
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: { can: () => false } as never,
      permissionsLoaded: true,
    });
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText("visibility: PRIVATE")).toBeInTheDocument();
    });

    expect(screen.queryByTestId("template-visibility-select")).not.toBeInTheDocument();
  });

  it("shows Save button when visibility is changed", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await screen.findByTestId("template-visibility-select");
    expect(screen.queryByTestId("template-save-visibility-button")).not.toBeInTheDocument();

    fireEvent.mouseDown(visibilityCombobox());
    const publicOption = await screen.findByRole("option", { name: "public_authenticated_users" });
    fireEvent.click(publicOption);

    await waitFor(() => {
      expect(screen.getByTestId("template-save-visibility-button")).toBeInTheDocument();
    });

    expect(TemplateService.updateTemplate).not.toHaveBeenCalled();
  });

  it("calls updateTemplate when Save button is clicked", async () => {
    const updatedPayload = templatePayload({ visibility: "PUBLIC" });
    vi.mocked(TemplateService.updateTemplate).mockResolvedValue(updatedPayload as never);

    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await screen.findByTestId("template-visibility-select");

    fireEvent.mouseDown(visibilityCombobox());
    const publicOption = await screen.findByRole("option", { name: "public_authenticated_users" });
    fireEvent.click(publicOption);

    await waitFor(() => {
      expect(screen.getByTestId("template-save-visibility-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("template-save-visibility-button"));

    await waitFor(() => {
      expect(TemplateService.updateTemplate).toHaveBeenCalledWith(5, { visibility: "PUBLIC" });
    });

    await waitFor(() => {
      expect(screen.getByText("Visibility updated successfully.")).toBeInTheDocument();
    });
  });

  it("shows error alert when visibility update fails", async () => {
    vi.mocked(TemplateService.updateTemplate).mockRejectedValue(new Error("Permission denied"));

    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await screen.findByTestId("template-visibility-select");

    fireEvent.mouseDown(visibilityCombobox());
    const tenantOption = await screen.findByRole("option", { name: "tenant_wide" });
    fireEvent.click(tenantOption);

    await waitFor(() => {
      expect(screen.getByTestId("template-save-visibility-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("template-save-visibility-button"));

    await waitFor(() => {
      expect(screen.getByText("Permission denied")).toBeInTheDocument();
    });
  });

  it("hides Save button when visibility is changed back to original", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as never);
    });

    renderWithRouter(<TemplateModelerPage />);

    await screen.findByTestId("template-visibility-select");

    fireEvent.mouseDown(visibilityCombobox());
    const publicOption = await screen.findByRole("option", { name: "public_authenticated_users" });
    fireEvent.click(publicOption);

    await waitFor(() => {
      expect(screen.getByTestId("template-save-visibility-button")).toBeInTheDocument();
    });

    fireEvent.mouseDown(visibilityCombobox());
    const privateOption = await screen.findByRole("option", { name: "private_only_you" });
    fireEvent.click(privateOption);

    await waitFor(() => {
      expect(screen.queryByTestId("template-save-visibility-button")).not.toBeInTheDocument();
    });
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import type React from "react";
import TemplateModelerPage from "./TemplateModelerPage";

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

describe("TemplateModelerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useParams).mockReturnValue({ templateId: "5" });
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload() as any);
    });
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: { can: () => true } as any,
      permissionsLoaded: true,
    });
  });

  it("renders template name and does not show Delete button", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText(/Template: Test Template/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("shows Publish button when template is not published", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Publish" })).toBeInTheDocument();
    });
  });

  it("does not show Publish button when template is published", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText(/Template: Test Template/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });

  it("shows visibility dropdown for draft template when user has edit permission", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "TENANT" }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    expect(screen.queryByText("Visibility: TENANT")).not.toBeInTheDocument();
  });

  it("shows read-only visibility chip for published template", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true, visibility: "TENANT" }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText("Visibility: TENANT")).toBeInTheDocument();
    });

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows read-only visibility chip when user lacks edit permission", async () => {
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: { can: () => false } as any,
      permissionsLoaded: true,
    });
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText("Visibility: PRIVATE")).toBeInTheDocument();
    });

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows Save button when visibility is changed", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const publicOption = await screen.findByRole("option", { name: /Public/i });
    fireEvent.click(publicOption);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });

    expect(TemplateService.updateTemplate).not.toHaveBeenCalled();
  });

  it("calls updateTemplate when Save button is clicked", async () => {
    const updatedPayload = templatePayload({ visibility: "PUBLIC" });
    vi.mocked(TemplateService.updateTemplate).mockResolvedValue(updatedPayload as any);

    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const publicOption = await screen.findByRole("option", { name: /Public/i });
    fireEvent.click(publicOption);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

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
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const tenantOption = await screen.findByRole("option", { name: /Tenant-wide/i });
    fireEvent.click(tenantOption);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(screen.getByText("Permission denied")).toBeInTheDocument();
    });
  });

  it("hides Save button when visibility is changed back to original", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false, visibility: "PRIVATE" }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const publicOption = await screen.findByRole("option", { name: /Public/i });
    fireEvent.click(publicOption);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const privateOption = await screen.findByRole("option", { name: /Private/i });
    fireEvent.click(privateOption);

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    });
  });
});

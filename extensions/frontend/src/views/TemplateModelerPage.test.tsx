import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, useParams, useNavigate } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import type React from "react";
import TemplateModelerPage from "./TemplateModelerPage";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useParams: vi.fn(),
    useNavigate: vi.fn(() => mockNavigate),
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
    deleteTemplate: vi.fn(),
    exportTemplate: vi.fn(),
  },
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

import HttpService from "../services/HttpService";
import TemplateService from "../services/TemplateService";

const theme = createTheme();

function templatePayload(overrides: { isPublished?: boolean; name?: string } = {}) {
  return {
    id: 5,
    templateKey: "test-key",
    name: overrides.name ?? "Test Template",
    version: "V1",
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
    vi.mocked(useParams).mockReturnValue({ templateId: "5" });
    mockNavigate.mockClear();
    vi.mocked(TemplateService.deleteTemplate).mockResolvedValue(undefined);
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload() as any);
    });
  });

  it("shows Delete button when template is not published", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: false }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    });
  });

  it("does not show Delete button when template is published", async () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(templatePayload({ isPublished: true }) as any);
    });

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByText(/Template: Test Template/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("opens confirmation dialog when Delete is clicked", async () => {
    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Delete Template")).toBeInTheDocument();
    expect(screen.getByText(/Are you sure you want to delete the template/)).toBeInTheDocument();
  });

  it("closes dialog and does not call deleteTemplate when Cancel is clicked", async () => {
    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    expect(TemplateService.deleteTemplate).not.toHaveBeenCalled();
  });

  it("calls deleteTemplate and navigates to /templates when Confirm Delete is clicked", async () => {
    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    const dialog = screen.getByRole("dialog");
    const confirmDelete = within(dialog).getByRole("button", { name: "Delete" });
    fireEvent.click(confirmDelete);

    await waitFor(() => {
      expect(TemplateService.deleteTemplate).toHaveBeenCalledWith(5);
    });

    expect(mockNavigate).toHaveBeenCalledWith("/templates");
  });

  it("shows error and does not navigate when deleteTemplate rejects", async () => {
    vi.mocked(TemplateService.deleteTemplate).mockRejectedValue(
      new Error("Server error")
    );

    renderWithRouter(<TemplateModelerPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    const confirmDelete = within(dialog).getByRole("button", { name: "Delete" });
    fireEvent.click(confirmDelete);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Server error|Failed to delete template/)
    ).toBeInTheDocument();
  });
});

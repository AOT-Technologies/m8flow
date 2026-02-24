import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, useParams, useNavigate } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import type React from "react";
import TemplateFileDiagramPage from "./TemplateFileDiagramPage";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
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
    getTemplateFileContent: vi.fn(),
    updateTemplateFile: vi.fn(),
  },
}));

vi.mock("@spiffworkflow-frontend/components/ProcessBreadcrumb", () => ({
  default: () => <div data-testid="breadcrumb">Breadcrumb</div>,
}));

vi.mock("@spiffworkflow-frontend/components/ReactDiagramEditor", () => ({
  default: function MockReactDiagramEditor({
    onLaunchJsonSchemaEditor,
  }: {
    onLaunchJsonSchemaEditor?: (
      el: unknown,
      fileName: string,
      eventBus: unknown
    ) => void;
  }) {
    return (
      <div data-testid="mock-diagram-editor">
        <button
          type="button"
          onClick={() =>
            onLaunchJsonSchemaEditor?.(null, "my-form-schema.json", {})
          }
        >
          Launch schema editor
        </button>
        <button
          type="button"
          onClick={() =>
            onLaunchJsonSchemaEditor?.(null, "file name.json", {})
          }
        >
          Launch schema editor with space
        </button>
      </div>
    );
  },
}));

import HttpService from "../services/HttpService";
import TemplateService from "../services/TemplateService";

const theme = createTheme();

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>{ui}</MemoryRouter>
    </ThemeProvider>
  );
}

const minimalTemplate = {
  id: 5,
  name: "Test Template",
  version: "V1",
  files: [],
  createdAt: "2024-01-01T00:00:00.000Z",
  updatedAt: "2024-01-01T00:00:00.000Z",
};

describe("TemplateFileDiagramPage", () => {
  beforeEach(() => {
    vi.mocked(useParams).mockReturnValue({
      templateId: "5",
      fileName: "diagram.bpmn",
    });
    mockNavigate.mockClear();
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
      opts.successCallback?.(minimalTemplate as any);
    });
    vi.mocked(TemplateService.getTemplateFileContent).mockResolvedValue(
      "<xml/>"
    );
  });

  it("navigates to form editor when Launch Editor is clicked", async () => {
    renderWithRouter(<TemplateFileDiagramPage />);

    await waitFor(() => {
      expect(screen.getByTestId("mock-diagram-editor")).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Launch schema editor" })
    );

    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith(
      "/templates/5/form/my-form-schema.json"
    );
  });

  it("encodes schema file name in navigation path when it contains special characters", async () => {
    renderWithRouter(<TemplateFileDiagramPage />);

    await waitFor(() => {
      expect(screen.getByTestId("mock-diagram-editor")).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Launch schema editor with space/i })
    );

    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith(
      "/templates/5/form/file%20name.json"
    );
  });
});

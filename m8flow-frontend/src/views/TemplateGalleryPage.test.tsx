import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import type React from "react";
import TemplateGalleryPage from "./TemplateGalleryPage";

vi.mock("react-router-dom", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: vi.fn(() => vi.fn()),
  };
});

vi.mock("../hooks/useTemplates", () => ({
  useTemplates: vi.fn(),
}));

vi.mock("../services/TemplateService", () => ({
  default: {
    deleteTemplate: vi.fn(() => Promise.resolve()),
    restoreTemplate: vi.fn(() => Promise.resolve({})),
  },
}));

vi.mock("../services/UserService", () => ({
  default: {
    getUserName: vi.fn(() => "tester"),
    getPreferredUsername: vi.fn(() => "tester"),
  },
}));

vi.mock("../services/HttpService", () => ({
  default: {
    HttpMethods: { GET: "GET" },
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock("@spiffworkflow-frontend/hooks/PermissionService", () => ({
  usePermissionFetcher: vi.fn(() => ({
    ability: { can: () => true },
    permissionsLoaded: true,
  })),
}));

vi.mock("../components/TemplateFilters", () => ({
  default: () => <div data-testid="template-filters-mock">filters</div>,
}));

vi.mock("../components/ImportTemplateModal", () => ({
  default: () => null,
}));

vi.mock("@spiffworkflow-frontend/components/PaginationForTable", () => ({
  default: ({ tableToDisplay }: { tableToDisplay: React.ReactNode }) => (
    <div data-testid="pagination-mock">{tableToDisplay}</div>
  ),
}));

vi.mock("../components/TemplateCard", () => ({
  default: ({
    template,
    onDeleteTemplate,
    onRestoreTemplate,
    deleteDisabled,
    restoreDisabled,
  }: any) => (
    <div data-testid={`template-card-${template.id}`}>
      {onDeleteTemplate ? (
        <button
          data-testid={`template-card-delete-${template.id}`}
          disabled={deleteDisabled}
          onClick={onDeleteTemplate}
          type="button"
        >
          Delete
        </button>
      ) : null}
      {onRestoreTemplate ? (
        <button
          data-testid={`template-card-restore-${template.id}`}
          disabled={restoreDisabled}
          onClick={onRestoreTemplate}
          type="button"
        >
          Restore
        </button>
      ) : null}
    </div>
  ),
}));

import { useTemplates } from "../hooks/useTemplates";
import HttpService from "../services/HttpService";
import TemplateService from "../services/TemplateService";
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";

const theme = createTheme();
const fetchTemplatesMock = vi.fn();

function makeTemplate(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    templateKey: "template-a",
    version: "V1",
    name: "Template A",
    description: null,
    tags: [],
    category: null,
    tenantId: "tenant-a",
    visibility: "TENANT",
    files: [],
    isPublished: false,
    status: "draft",
    createdAtInSeconds: 1700000000,
    updatedAtInSeconds: 1700000100,
    createdBy: "tester",
    modifiedBy: "tester",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter>
        <TemplateGalleryPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("TemplateGalleryPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.mocked(HttpService.makeCallToBackend).mockImplementation(() => {});
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: { can: () => true } as any,
      permissionsLoaded: true,
    });
    vi.mocked(useTemplates).mockReturnValue({
      templates: [makeTemplate()],
      pagination: { count: 1, total: 1, pages: 1 },
      templatesLoading: false,
      templateByIdLoading: false,
      templateByKeyLoading: false,
      error: null,
      fetchTemplates: fetchTemplatesMock,
      fetchTemplateById: vi.fn(),
      fetchTemplateByKey: vi.fn(),
    } as any);
  });

  it("calls delete API from table action and refreshes list", async () => {
    renderPage();
    fireEvent.click(screen.getByTestId("template-gallery-view-table"));
    fireEvent.click(screen.getByTestId("template-gallery-delete-button-1"));

    await waitFor(() => {
      expect(TemplateService.deleteTemplate).toHaveBeenCalledWith(1);
    });
    expect(fetchTemplatesMock).toHaveBeenCalled();
  });

  it("disables published delete for users without admin permission in table view", async () => {
    // No admin permission (ability.can returns false for /m8flow/admin/templates)
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: {
        can: (method: string, uri: string) => {
          if (uri === "/m8flow/admin/templates") return false;
          return true;
        },
      } as any,
      permissionsLoaded: true,
    });
    vi.mocked(useTemplates).mockReturnValue({
      templates: [makeTemplate({ isPublished: true })],
      pagination: { count: 1, total: 1, pages: 1 },
      templatesLoading: false,
      templateByIdLoading: false,
      templateByKeyLoading: false,
      error: null,
      fetchTemplates: fetchTemplatesMock,
      fetchTemplateById: vi.fn(),
      fetchTemplateByKey: vi.fn(),
    } as any);

    renderPage();
    fireEvent.click(screen.getByTestId("template-gallery-view-table"));

    const deleteButton = await screen.findByTestId("template-gallery-delete-button-1");
    expect(deleteButton).toBeDisabled();
  });

  it("calls delete API from card action in active mode", async () => {
    renderPage();
    fireEvent.click(screen.getByTestId("template-card-delete-1"));

    await waitFor(() => {
      expect(TemplateService.deleteTemplate).toHaveBeenCalledWith(1);
    });
  });

  it("shows deleted mode restore action and calls restore API", async () => {
    // Admin permission (ability.can returns true for all URIs)
    vi.mocked(usePermissionFetcher).mockReturnValue({
      ability: { can: () => true } as any,
      permissionsLoaded: true,
    });
    vi.mocked(useTemplates).mockReturnValue({
      templates: [makeTemplate({ isPublished: true, status: "published" })],
      pagination: { count: 1, total: 1, pages: 1 },
      templatesLoading: false,
      templateByIdLoading: false,
      templateByKeyLoading: false,
      error: null,
      fetchTemplates: fetchTemplatesMock,
      fetchTemplateById: vi.fn(),
      fetchTemplateByKey: vi.fn(),
    } as any);

    renderPage();
    fireEvent.click(screen.getByTestId("template-gallery-mode-deleted"));
    fireEvent.click(screen.getByTestId("template-card-restore-1"));

    await waitFor(() => {
      expect(TemplateService.restoreTemplate).toHaveBeenCalledWith(1);
    });
    expect(fetchTemplatesMock).toHaveBeenCalled();
  });
});

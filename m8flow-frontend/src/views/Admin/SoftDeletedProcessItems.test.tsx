import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SoftDeletedProcessItems from "./SoftDeletedProcessItems";

const mockMakeCallToBackend = vi.fn();

vi.mock("../../services/HttpService", () => ({
  default: {
    makeCallToBackend: (...args: unknown[]) => mockMakeCallToBackend(...args),
  },
}));

vi.mock("../../hooks/UseApiError", () => ({
  default: () => ({
    addError: vi.fn(),
    removeError: vi.fn(),
  }),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) =>
      opts?.defaultValue || key,
    i18n: { changeLanguage: vi.fn() },
  }),
}));

describe("SoftDeletedProcessItems", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the page title", () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }) => {
      successCallback({ results: [], pagination: { count: 0, total: 0, pages: 0, page: 1 } });
    });

    render(<SoftDeletedProcessItems />);
    expect(screen.getByText("Deleted Process Models & Groups")).toBeInTheDocument();
  });

  it("shows empty message when no deleted models", async () => {
    mockMakeCallToBackend.mockImplementation(({ successCallback }) => {
      successCallback({ results: [], pagination: { count: 0, total: 0, pages: 0, page: 1 } });
    });

    render(<SoftDeletedProcessItems />);
    await waitFor(() => {
      expect(screen.getByText("No soft-deleted process models found.")).toBeInTheDocument();
    });
  });

  it("displays deleted models in the table", async () => {
    const deletedModels = [
      {
        id: 1,
        original_identifier: "group1/model1",
        deleted_identifier: "group1/model1_deleted_1716000000",
        display_name: "Model One",
        parent_group_id: "group1",
        status: "SOFT_DELETED",
        deleted_at_in_seconds: 1716000000,
        deleted_by: "admin@test.com",
        m8f_tenant_id: "tenant-1",
      },
    ];

    mockMakeCallToBackend.mockImplementation(({ path, successCallback }) => {
      if (path.includes("process-models")) {
        successCallback({ results: deletedModels, pagination: { count: 1, total: 1, pages: 1, page: 1 } });
      } else {
        successCallback({ results: [], pagination: { count: 0, total: 0, pages: 0, page: 1 } });
      }
    });

    render(<SoftDeletedProcessItems />);
    await waitFor(() => {
      expect(screen.getByText("Model One")).toBeInTheDocument();
      expect(screen.getByText("group1/model1")).toBeInTheDocument();
    });
  });

  it("opens restore conflict dialog on 409 response", async () => {
    const deletedModels = [
      {
        id: 1,
        original_identifier: "group1/model1",
        deleted_identifier: "group1/model1_deleted_1716000000",
        display_name: "Model One",
        parent_group_id: "group1",
        status: "SOFT_DELETED",
        deleted_at_in_seconds: 1716000000,
        deleted_by: "admin@test.com",
        m8f_tenant_id: "tenant-1",
      },
    ];

    let callCount = 0;
    mockMakeCallToBackend.mockImplementation(({ path, httpMethod, successCallback, failureCallback }) => {
      if (httpMethod === "POST" && path.includes("restore")) {
        failureCallback({ error_code: "original_name_in_use", message: "Name already in use" });
        return;
      }
      if (path.includes("process-models")) {
        successCallback({ results: deletedModels, pagination: { count: 1, total: 1, pages: 1, page: 1 } });
      } else {
        successCallback({ results: [], pagination: { count: 0, total: 0, pages: 0, page: 1 } });
      }
    });

    render(<SoftDeletedProcessItems />);

    await waitFor(() => {
      expect(screen.getByText("Model One")).toBeInTheDocument();
    });

    const restoreButtons = screen.getAllByText("Restore");
    fireEvent.click(restoreButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Restore with New Name")).toBeInTheDocument();
      expect(screen.getByText("Name already in use")).toBeInTheDocument();
    });
  });
});

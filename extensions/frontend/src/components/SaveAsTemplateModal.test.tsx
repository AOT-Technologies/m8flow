import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import type React from "react";
import SaveAsTemplateModal from "./SaveAsTemplateModal";

vi.mock("../services/TemplateService", () => ({
  default: {
    createTemplate: vi.fn(),
  },
}));

import TemplateService from "../services/TemplateService";

const theme = createTheme();

function renderWithTheme(ui: React.ReactElement) {
  return render(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);
}

function typeInField(label: string | RegExp, value: string) {
  const field = screen.getByLabelText(label);
  fireEvent.change(field, { target: { value } });
}

describe("SaveAsTemplateModal", () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    getBpmnXml: vi.fn().mockResolvedValue("<bpmn:definitions/>"),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(defaultProps.onClose).mockClear();
    vi.mocked(defaultProps.getBpmnXml).mockClear().mockResolvedValue("<bpmn:definitions/>");
    vi.mocked(TemplateService.createTemplate).mockResolvedValue({
      id: 1,
      templateKey: "test-key",
      name: "Test Template",
      version: "V1",
      visibility: "PRIVATE",
    } as any);
  });

  it("renders dialog with title and form fields when open", () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    expect(screen.getByText("Save as Template")).toBeInTheDocument();
    expect(screen.getByLabelText(/Template key/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tags/i)).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create Template/i })).toBeInTheDocument();
  });

  it("does not render dialog content when open is false", () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} open={false} />);
    expect(screen.queryByText("Save as Template")).not.toBeInTheDocument();
  });

  it("shows validation error when template key is empty on submit", async () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    typeInField(/Name/i, "My Template");
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(screen.getByText("Template key is required.")).toBeInTheDocument();
    });
    expect(TemplateService.createTemplate).not.toHaveBeenCalled();
  });

  it("shows validation error when name is empty on submit", async () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    typeInField(/Template key/i, "my-key");
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(screen.getByText("Name is required.")).toBeInTheDocument();
    });
    expect(TemplateService.createTemplate).not.toHaveBeenCalled();
  });

  it("calls getBpmnXml and createTemplate with trimmed key and name on submit", async () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    typeInField(/Template key/i, "  my-key  ");
    typeInField(/Name/i, "  My Template  ");
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(defaultProps.getBpmnXml).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(TemplateService.createTemplate).toHaveBeenCalledWith(
        "<bpmn:definitions/>",
        expect.objectContaining({
          template_key: "my-key",
          name: "My Template",
          visibility: "PRIVATE",
        })
      );
    });
  });

  it("includes optional description, category, and tags in metadata when provided", async () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    typeInField(/Template key/i, "my-key");
    typeInField(/Name/i, "My Template");
    typeInField(/Description/i, "A description");
    typeInField(/Category/i, "Approval");
    typeInField(/Tags/i, "tag1, tag2 , tag3");
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(TemplateService.createTemplate).toHaveBeenCalledWith(
        "<bpmn:definitions/>",
        expect.objectContaining({
          template_key: "my-key",
          name: "My Template",
          description: "A description",
          category: "Approval",
          tags: ["tag1", "tag2", "tag3"],
        })
      );
    });
  });

  it("shows error when getBpmnXml returns empty string", async () => {
    vi.mocked(defaultProps.getBpmnXml).mockResolvedValue("");
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    typeInField(/Template key/i, "my-key");
    typeInField(/Name/i, "My Template");
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(screen.getByText("Could not get diagram content. Please try again.")).toBeInTheDocument();
    });
    expect(TemplateService.createTemplate).not.toHaveBeenCalled();
  });

  it("shows error when createTemplate rejects", async () => {
    vi.mocked(TemplateService.createTemplate).mockRejectedValue(new Error("Server error"));
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    typeInField(/Template key/i, "my-key");
    typeInField(/Name/i, "My Template");
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(screen.getByText("Server error")).toBeInTheDocument();
    });
  });

  it("calls onClose and onSuccess with template when create succeeds", async () => {
    const onSuccess = vi.fn();
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} onSuccess={onSuccess} />);
    typeInField(/Template key/i, "my-key");
    typeInField(/Name/i, "My Template");
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(defaultProps.onClose).toHaveBeenCalled();
      expect(onSuccess).toHaveBeenCalledWith(
        expect.objectContaining({ id: 1, templateKey: "test-key", name: "Test Template" })
      );
    });
  });

  it("Cancel button calls onClose", () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it("sends selected visibility in metadata", async () => {
    renderWithTheme(<SaveAsTemplateModal {...defaultProps} />);
    typeInField(/Template key/i, "my-key");
    typeInField(/Name/i, "My Template");
    const visibilityTrigger = screen.getByRole("combobox");
    fireEvent.mouseDown(visibilityTrigger);
    const tenantOption = await screen.findByRole("option", { name: /Tenant-wide/i });
    fireEvent.click(tenantOption);
    fireEvent.click(screen.getByRole("button", { name: /Create Template/i }));
    await waitFor(() => {
      expect(TemplateService.createTemplate).toHaveBeenCalledWith(
        "<bpmn:definitions/>",
        expect.objectContaining({ visibility: "TENANT" })
      );
    });
  });
});

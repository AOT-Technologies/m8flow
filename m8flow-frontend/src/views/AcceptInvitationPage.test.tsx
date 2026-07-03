import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AcceptInvitationPage from "./AcceptInvitationPage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockValidateInvitation = vi.fn();
const mockAcceptInvitation = vi.fn();

vi.mock("../services/TenantService", () => ({
  default: {
    validateInvitation: (...args: unknown[]) => mockValidateInvitation(...args),
    acceptInvitation: (...args: unknown[]) => mockAcceptInvitation(...args),
  },
}));

const setToken = (token: string | null) => {
  const search = token === null ? "" : `?token=${token}`;
  window.history.replaceState({}, "", `/accept-invitation${search}`);
};

const VALIDATION = {
  email: "user@example.com",
  tenant_id: "tenant-1",
  tenant_name: "Acme Corp",
  roles: ["editor", "viewer"] as const,
  expires_at_in_seconds: 123,
};

describe("AcceptInvitationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setToken("raw-token");
  });

  it("shows an error and skips validation when the token is missing", async () => {
    setToken(null);
    render(<AcceptInvitationPage />);

    expect(await screen.findByTestId("accept-invitation-error")).toBeInTheDocument();
    expect(mockValidateInvitation).not.toHaveBeenCalled();
  });

  it("renders the invitation metadata once the token validates", async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    render(<AcceptInvitationPage />);

    expect(await screen.findByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByText("editor")).toBeInTheDocument();
    expect(screen.getByText("viewer")).toBeInTheDocument();
    expect(mockValidateInvitation).toHaveBeenCalledWith("raw-token");
  });

  it("shows the validation error when the token is invalid", async () => {
    mockValidateInvitation.mockRejectedValue({ message: "This invitation link has expired." });
    render(<AcceptInvitationPage />);

    expect(
      await screen.findByText("This invitation link has expired."),
    ).toBeInTheDocument();
  });

  it("disables submit until the password is long enough and confirmation matches", async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    render(<AcceptInvitationPage />);
    await screen.findByText("Acme Corp");

    const submit = screen.getByTestId("accept-invitation-submit");
    const password = screen.getByTestId("accept-invitation-password");
    const confirm = screen.getByTestId("accept-invitation-confirm-password");

    expect(submit).toBeDisabled();

    fireEvent.change(password, { target: { value: "short" } });
    fireEvent.change(confirm, { target: { value: "short" } });
    expect(submit).toBeDisabled(); // too short

    fireEvent.change(password, { target: { value: "password123" } });
    fireEvent.change(confirm, { target: { value: "mismatch123" } });
    expect(submit).toBeDisabled(); // mismatch

    fireEvent.change(confirm, { target: { value: "password123" } });
    expect(submit).toBeEnabled();
  });

  it("activates the account on a successful accept", async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    mockAcceptInvitation.mockResolvedValue({ smtp_configured: false });
    render(<AcceptInvitationPage />);
    await screen.findByText("Acme Corp");

    fireEvent.change(screen.getByTestId("accept-invitation-password"), {
      target: { value: "password123" },
    });
    fireEvent.change(screen.getByTestId("accept-invitation-confirm-password"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByTestId("accept-invitation-submit"));

    await waitFor(() => {
      expect(mockAcceptInvitation).toHaveBeenCalledWith("raw-token", "password123");
    });
    expect(
      await screen.findByTestId("accept-invitation-go-login"),
    ).toBeInTheDocument();
  });

  it("shows the submit error when accepting fails", async () => {
    mockValidateInvitation.mockResolvedValue(VALIDATION);
    mockAcceptInvitation.mockRejectedValue({ message: "Failed to activate your account." });
    render(<AcceptInvitationPage />);
    await screen.findByText("Acme Corp");

    fireEvent.change(screen.getByTestId("accept-invitation-password"), {
      target: { value: "password123" },
    });
    fireEvent.change(screen.getByTestId("accept-invitation-confirm-password"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByTestId("accept-invitation-submit"));

    expect(
      await screen.findByText("Failed to activate your account."),
    ).toBeInTheDocument();
  });
});

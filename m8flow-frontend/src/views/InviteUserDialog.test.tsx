import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InviteUserDialog from "./InviteUserDialog";

vi.mock("react-i18next", () => ({
  // Return the key so the component's translate(key, fallback) helper uses its fallback.
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockCreateInvitation = vi.fn();

vi.mock("../services/TenantService", () => ({
  TENANT_MEMBER_ROLES: [
    "tenant-admin",
    "editor",
    "integrator",
    "reviewer",
    "submitter",
    "viewer",
  ],
  default: {
    createInvitation: (...args: unknown[]) => mockCreateInvitation(...args),
  },
}));

function renderDialog(overrides: Partial<Parameters<typeof InviteUserDialog>[0]> = {}) {
  const props = {
    open: true,
    tenantId: "tenant-1",
    onClose: vi.fn(),
    onInvited: vi.fn(),
    ...overrides,
  };
  render(<InviteUserDialog {...props} />);
  return props;
}

const toggleRole = (roleName: string) => {
  const checkbox = within(screen.getByTestId(`invite-user-role-${roleName}`)).getByRole(
    "checkbox",
  );
  fireEvent.click(checkbox);
};

describe("InviteUserDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the submit button disabled until a valid email and a role are provided", () => {
    renderDialog();
    const submit = screen.getByTestId("invite-user-submit");
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId("invite-user-email-input"), {
      target: { value: "user@example.com" },
    });
    // Email alone is not enough.
    expect(submit).toBeDisabled();

    toggleRole("editor");
    expect(submit).toBeEnabled();
  });

  it("keeps submit disabled for an invalid email even with a role selected", () => {
    renderDialog();
    fireEvent.change(screen.getByTestId("invite-user-email-input"), {
      target: { value: "not-an-email" },
    });
    toggleRole("editor");
    expect(screen.getByTestId("invite-user-submit")).toBeDisabled();
  });

  it("sends the invitation and notifies the parent on success", async () => {
    mockCreateInvitation.mockResolvedValue({ id: "inv-1", status: "PENDING" });
    const { onInvited, onClose } = renderDialog();

    fireEvent.change(screen.getByTestId("invite-user-email-input"), {
      target: { value: "user@example.com" },
    });
    toggleRole("editor");
    fireEvent.click(screen.getByTestId("invite-user-submit"));

    await waitFor(() => {
      expect(mockCreateInvitation).toHaveBeenCalledWith("tenant-1", {
        email: "user@example.com",
        roles: ["editor"],
        validity_days: 7,
      });
    });
    expect(onInvited).toHaveBeenCalled();
    // No dev link in the response, so the dialog closes.
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("surfaces the dev-mode link instead of closing when SMTP is not configured", async () => {
    mockCreateInvitation.mockResolvedValue({
      id: "inv-1",
      status: "PENDING",
      invitation_link: "http://localhost:6841/accept-invitation?token=abc",
    });
    const { onInvited, onClose } = renderDialog();

    fireEvent.change(screen.getByTestId("invite-user-email-input"), {
      target: { value: "user@example.com" },
    });
    toggleRole("editor");
    fireEvent.click(screen.getByTestId("invite-user-submit"));

    expect(
      await screen.findByDisplayValue(
        "http://localhost:6841/accept-invitation?token=abc",
      ),
    ).toBeInTheDocument();
    expect(onInvited).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("Done")).toBeInTheDocument();
  });

  it("renders the error message when sending the invitation fails", async () => {
    mockCreateInvitation.mockRejectedValue({ detail: "A user with email already exists." });
    renderDialog();

    fireEvent.change(screen.getByTestId("invite-user-email-input"), {
      target: { value: "user@example.com" },
    });
    toggleRole("editor");
    fireEvent.click(screen.getByTestId("invite-user-submit"));

    expect(
      await screen.findByText("A user with email already exists."),
    ).toBeInTheDocument();
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PendingInvitationsPanel from "./PendingInvitationsPanel";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockListInvitations = vi.fn();
const mockResendInvitation = vi.fn();
const mockRevokeInvitation = vi.fn();

vi.mock("../services/TenantService", () => ({
  default: {
    listInvitations: (...args: unknown[]) => mockListInvitations(...args),
    resendInvitation: (...args: unknown[]) => mockResendInvitation(...args),
    revokeInvitation: (...args: unknown[]) => mockRevokeInvitation(...args),
  },
}));

const invitation = (overrides: Record<string, unknown> = {}) => ({
  id: "inv-1",
  tenant_id: "tenant-1",
  email: "user@example.com",
  roles: ["editor"],
  status: "PENDING",
  expires_at_in_seconds: 1_900_000_000,
  accepted_at_in_seconds: null,
  created_by: "admin",
  created_at_in_seconds: 1_800_000_000,
  ...overrides,
});

const page = (results: unknown[]) => ({
  results,
  total: results.length,
  offset: 0,
  limit: 100,
});

function renderPanel() {
  render(<PendingInvitationsPanel tenantId="tenant-1" refreshKey={0} />);
}

describe("PendingInvitationsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and renders invitation rows", async () => {
    mockListInvitations.mockResolvedValue(
      page([invitation(), invitation({ id: "inv-2", email: "two@example.com", status: "ACCEPTED" })]),
    );
    renderPanel();

    expect(await screen.findByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByText("two@example.com")).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();
    expect(screen.getByText("ACCEPTED")).toBeInTheDocument();
    expect(mockListInvitations).toHaveBeenCalledWith("tenant-1", { limit: 100 });
  });

  it("shows the empty state when there are no invitations", async () => {
    mockListInvitations.mockResolvedValue(page([]));
    renderPanel();

    expect(await screen.findByText("No invitations yet.")).toBeInTheDocument();
  });

  it("resends an invitation and reloads the list", async () => {
    mockListInvitations.mockResolvedValue(page([invitation()]));
    mockResendInvitation.mockResolvedValue(invitation());
    renderPanel();

    await screen.findByText("user@example.com");
    fireEvent.click(screen.getByTestId("invitation-resend-inv-1"));

    await waitFor(() => {
      expect(mockResendInvitation).toHaveBeenCalledWith("tenant-1", "inv-1");
    });
    // Initial load + reload after resend.
    await waitFor(() => expect(mockListInvitations).toHaveBeenCalledTimes(2));
  });

  it("revokes an invitation and reloads the list", async () => {
    mockListInvitations.mockResolvedValue(page([invitation()]));
    mockRevokeInvitation.mockResolvedValue(invitation({ status: "REVOKED" }));
    renderPanel();

    await screen.findByText("user@example.com");
    fireEvent.click(screen.getByTestId("invitation-revoke-inv-1"));

    await waitFor(() => {
      expect(mockRevokeInvitation).toHaveBeenCalledWith("tenant-1", "inv-1");
    });
    await waitFor(() => expect(mockListInvitations).toHaveBeenCalledTimes(2));
  });

  it("disables resend for accepted invitations and revoke for non-pending ones", async () => {
    mockListInvitations.mockResolvedValue(
      page([invitation({ id: "inv-acc", status: "ACCEPTED" })]),
    );
    renderPanel();

    await screen.findByText("user@example.com");
    expect(screen.getByTestId("invitation-resend-inv-acc")).toBeDisabled();
    expect(screen.getByTestId("invitation-revoke-inv-acc")).toBeDisabled();
  });

  it("renders an error alert when loading fails", async () => {
    mockListInvitations.mockRejectedValue({ detail: "Failed to load invitations." });
    renderPanel();

    expect(await screen.findByText("Failed to load invitations.")).toBeInTheDocument();
  });
});

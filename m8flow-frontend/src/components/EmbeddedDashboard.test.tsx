import { fireEvent, render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import EmbeddedDashboard from "./EmbeddedDashboard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: {} }),
}));

const SRC = "http://localhost:6850";

describe("EmbeddedDashboard", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("renders the iframe and an always-visible open-in-new-tab action", () => {
    render(<EmbeddedDashboard title="Flower" src={SRC} />);

    const iframe = screen.getByTestId("embedded-dashboard-iframe");
    expect(iframe.getAttribute("src")).toBe(SRC);
    // Header action is present even before any load/timeout outcome.
    expect(
      screen.getByTestId("embedded-dashboard-open-new-tab"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("embedded-dashboard-slow-notice"),
    ).not.toBeInTheDocument();
  });

  it("surfaces the slow/blocked notice after the timeout while keeping the iframe mounted", () => {
    vi.useFakeTimers();
    render(<EmbeddedDashboard title="Flower" src={SRC} loadTimeoutMs={1000} />);

    expect(
      screen.queryByTestId("embedded-dashboard-slow-notice"),
    ).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(
      screen.getByTestId("embedded-dashboard-slow-notice"),
    ).toBeInTheDocument();
    // The iframe is NOT unmounted — a slow-but-valid dashboard can still appear.
    expect(
      screen.getByTestId("embedded-dashboard-iframe"),
    ).toBeInTheDocument();
  });

  it("does not show the notice if the iframe loads before the timeout", () => {
    vi.useFakeTimers();
    render(<EmbeddedDashboard title="Flower" src={SRC} loadTimeoutMs={1000} />);

    act(() => {
      fireEvent.load(screen.getByTestId("embedded-dashboard-iframe"));
      vi.advanceTimersByTime(1000);
    });

    expect(
      screen.queryByTestId("embedded-dashboard-slow-notice"),
    ).not.toBeInTheDocument();
  });

  it("lets the user dismiss the slow/blocked notice", () => {
    vi.useFakeTimers();
    render(<EmbeddedDashboard title="Flower" src={SRC} loadTimeoutMs={1000} />);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    fireEvent.click(
      screen.getByTestId("embedded-dashboard-slow-notice-dismiss"),
    );

    expect(
      screen.queryByTestId("embedded-dashboard-slow-notice"),
    ).not.toBeInTheDocument();
  });
});

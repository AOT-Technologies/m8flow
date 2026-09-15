import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import MonitoringNatsPage from "./MonitoringNatsPage";

const mockUseConfig = vi.fn();
const mockIsSuperAdmin = vi.fn();

vi.mock("../utils/useConfig", () => ({
  useConfig: () => mockUseConfig(),
}));

vi.mock("../services/UserService", () => ({
  default: {
    isSuperAdmin: () => mockIsSuperAdmin(),
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: {} }),
}));

function renderAt() {
  return render(
    <MemoryRouter initialEntries={["/monitoring/nats"]}>
      <Routes>
        <Route path="/monitoring/nats" element={<MonitoringNatsPage />} />
        <Route path="/" element={<div data-testid="home-marker">home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MonitoringNatsPage", () => {
  afterEach(() => vi.clearAllMocks());

  it("embeds the NATS dashboard for super-admins when enabled", () => {
    mockIsSuperAdmin.mockReturnValue(true);
    mockUseConfig.mockReturnValue({
      NATS_UI_URL: "http://localhost:6852",
      NATS_MONITORING_ENABLED: true,
    });

    const { container } = renderAt();

    const iframe = container.querySelector(
      '[data-testid="embedded-dashboard-iframe"]',
    );
    expect(iframe?.getAttribute("src")).toBe("http://localhost:6852");
  });

  it("redirects to home when NATS monitoring is disabled", () => {
    mockIsSuperAdmin.mockReturnValue(true);
    mockUseConfig.mockReturnValue({
      NATS_UI_URL: "",
      NATS_MONITORING_ENABLED: false,
    });

    renderAt();

    expect(screen.getByTestId("home-marker")).toBeInTheDocument();
  });

  it("redirects non-super-admins to home even when enabled", () => {
    mockIsSuperAdmin.mockReturnValue(false);
    mockUseConfig.mockReturnValue({
      NATS_UI_URL: "http://localhost:6852",
      NATS_MONITORING_ENABLED: true,
    });

    renderAt();

    expect(screen.getByTestId("home-marker")).toBeInTheDocument();
  });
});

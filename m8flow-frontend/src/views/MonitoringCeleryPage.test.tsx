import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import MonitoringCeleryPage from "./MonitoringCeleryPage";

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
    <MemoryRouter initialEntries={["/monitoring/celery"]}>
      <Routes>
        <Route path="/monitoring/celery" element={<MonitoringCeleryPage />} />
        <Route path="/" element={<div data-testid="home-marker">home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MonitoringCeleryPage", () => {
  afterEach(() => vi.clearAllMocks());

  it("embeds the Flower dashboard for super-admins", () => {
    mockIsSuperAdmin.mockReturnValue(true);
    mockUseConfig.mockReturnValue({ CELERY_FLOWER_URL: "http://localhost:6850" });

    const { container } = renderAt();

    const iframe = container.querySelector(
      '[data-testid="embedded-dashboard-iframe"]',
    );
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute("src")).toBe("http://localhost:6850");
  });

  it("redirects non-super-admins to home", () => {
    mockIsSuperAdmin.mockReturnValue(false);
    mockUseConfig.mockReturnValue({ CELERY_FLOWER_URL: "http://localhost:6850" });

    renderAt();

    expect(screen.getByTestId("home-marker")).toBeInTheDocument();
  });

  it("shows a not-configured message when no Flower URL is set", () => {
    mockIsSuperAdmin.mockReturnValue(true);
    mockUseConfig.mockReturnValue({ CELERY_FLOWER_URL: "" });

    const { container } = renderAt();

    expect(
      container.querySelector('[data-testid="embedded-dashboard-iframe"]'),
    ).toBeNull();
    expect(
      screen.getByText("celery_monitoring_not_configured"),
    ).toBeInTheDocument();
  });
});

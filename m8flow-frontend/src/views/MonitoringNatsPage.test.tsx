import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import MonitoringNatsPage from "./MonitoringNatsPage";

const mockUseConfig = vi.fn();
const mockIsSuperAdmin = vi.fn();
const mockIsLoggedIn = vi.fn();
const mockGetOverview = vi.fn();
const mockGetStreams = vi.fn();
const mockGetTenants = vi.fn();
const mockGetEvents = vi.fn();
const mockGetEventSummary = vi.fn();

vi.mock("../utils/useConfig", () => ({
  useConfig: () => mockUseConfig(),
}));

vi.mock("../services/UserService", () => ({
  default: {
    isSuperAdmin: () => mockIsSuperAdmin(),
    isLoggedIn: () => mockIsLoggedIn(),
  },
}));

vi.mock("../services/NatsMonitoringService", () => ({
  default: {
    getOverview: () => mockGetOverview(),
    getStreams: () => mockGetStreams(),
    getTenants: () => mockGetTenants(),
    getEvents: (...args: any[]) => mockGetEvents(...args),
    getEventSummary: (...args: any[]) => mockGetEventSummary(...args),
  },
  NATS_EVENT_OUTCOMES: ["queued", "instantiated", "rejected_auth"],
  NATS_FAILURE_OUTCOMES: ["rejected_auth"],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: {} }),
}));

const OVERVIEW = {
  healthy: true,
  status: "ok",
  serverName: "NB123",
  serverId: "NB123",
  version: "2.10.29",
  uptime: "7m56s",
  startedAt: null,
  connections: 2,
  totalConnections: 5,
  subscriptions: 73,
  inMsgs: 18,
  outMsgs: 19,
  inBytes: 1684,
  outBytes: 4404,
  slowConsumers: 0,
  memoryBytes: 18649088,
  cpuPercent: 0,
  jetstream: {
    memoryBytes: 0,
    storageBytes: 17902,
    totalStreams: 3,
    totalConsumers: 2,
    totalMessages: 88,
    totalBytes: 17902,
  },
};

const STREAMS = {
  streams: [
    {
      name: "M8FLOW_EVENTS",
      account: "$G",
      subjects: ["m8flow.events.>"],
      isInternal: false,
      messages: 33,
      bytes: 17902,
      firstSeq: 1,
      lastSeq: 33,
      numSubjects: 4,
      numDeleted: 0,
      consumerCount: 1,
      createdAt: null,
      consumers: [
        {
          name: "m8flow-engine-consumer",
          streamName: "M8FLOW_EVENTS",
          filterSubject: null,
          pending: 3,
          unacked: 2,
          streamLag: 3,
          ackLag: 2,
          redelivered: 0,
          waiting: 0,
          deliveredStreamSeq: 30,
          deliveredConsumerSeq: 30,
          ackFloorStreamSeq: 28,
          lastActive: null,
          createdAt: null,
        },
      ],
    },
    {
      name: "KV_m8flow-dedup",
      account: "$G",
      subjects: ["$KV.m8flow-dedup.>"],
      isInternal: true,
      messages: 0,
      bytes: 0,
      firstSeq: 1,
      lastSeq: 27,
      numSubjects: 0,
      numDeleted: 0,
      consumerCount: 0,
      createdAt: null,
      consumers: [],
    },
  ],
  totals: {
    streams: 1,
    consumers: 1,
    messages: 33,
    bytes: 17902,
    pending: 3,
    unacked: 2,
    redelivered: 0,
    internalStreams: 1,
  },
  jetstream: OVERVIEW.jetstream,
};

const EVENTS = {
  results: [
    {
      id: 1,
      tenantId: "tenant-acme",
      eventId: "evt-1",
      worker: "consumer",
      streamSeq: 30,
      processIdentifier: "group/proc",
      username: "alice",
      outcome: "instantiated",
      duplicateCount: 0,
      errorMessage: null,
      processInstanceId: 4242,
      queuedAtInSeconds: 1785488891,
      completedAtInSeconds: 1785488893,
      updatedAtInSeconds: 1785488893,
    },
    {
      id: 2,
      tenantId: "tenant-acme",
      eventId: "evt-2",
      worker: "consumer",
      streamSeq: 31,
      processIdentifier: "group/proc",
      username: "bob",
      outcome: "rejected_auth",
      duplicateCount: 2,
      errorMessage: "invalid api_key",
      processInstanceId: null,
      queuedAtInSeconds: 1785488895,
      completedAtInSeconds: 1785488895,
      updatedAtInSeconds: 1785488895,
    },
  ],
  pagination: { page: 1, perPage: 25, total: 2, pages: 1 },
};

const SUMMARY = {
  byOutcome: { instantiated: 1, rejected_auth: 1 },
  total: 2,
  queued: 0,
  instantiated: 1,
  failed: 1,
  duplicateDeliveries: 2,
};

const TENANTS = [
  {
    tenantId: "tenant-acme",
    tenantSlug: "acme",
    queued: 1,
    instantiated: 4,
    failed: 1,
    total: 6,
    lastActivityInSeconds: 1785488900,
  },
  {
    tenantId: "tenant-globex",
    tenantSlug: "globex",
    queued: 0,
    instantiated: 2,
    failed: 0,
    total: 2,
    lastActivityInSeconds: 1785488800,
  },
];

function setup({
  superAdmin = true,
  monitoringEnabled = true,
  inspectionEnabled = false,
  grafanaUrl = "",
}: {
  superAdmin?: boolean;
  monitoringEnabled?: boolean;
  inspectionEnabled?: boolean;
  grafanaUrl?: string;
} = {}) {
  mockIsSuperAdmin.mockReturnValue(superAdmin);
  mockIsLoggedIn.mockReturnValue(true);
  mockUseConfig.mockReturnValue({
    NATS_MONITORING_ENABLED: monitoringEnabled,
    NATS_MESSAGE_INSPECTION_ENABLED: inspectionEnabled,
    GRAFANA_URL: grafanaUrl,
  });
  mockGetOverview.mockResolvedValue(OVERVIEW);
  mockGetStreams.mockResolvedValue(STREAMS);
  mockGetTenants.mockResolvedValue([]);
  mockGetEvents.mockResolvedValue(EVENTS);
  mockGetEventSummary.mockResolvedValue(SUMMARY);

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

  it("no longer embeds a third-party dashboard iframe", async () => {
    const { container } = setup();

    await waitFor(() => expect(screen.getByTestId("nats-overview")).toBeInTheDocument());
    expect(
      container.querySelector('[data-testid="embedded-dashboard-iframe"]'),
    ).toBeNull();
  });

  it("shows a not-configured message when monitoring is disabled", () => {
    setup({ monitoringEnabled: false });

    expect(screen.getByTestId("nats-monitoring-not-configured")).toBeInTheDocument();
  });

  it("renders every tab for a super-admin", async () => {
    setup();

    await waitFor(() => expect(screen.getByTestId("nats-tab-overview")).toBeInTheDocument());
    expect(screen.getByTestId("nats-tab-streams")).toBeInTheDocument();
    expect(screen.getByTestId("nats-tab-tenants")).toBeInTheDocument();
    expect(screen.getByTestId("nats-tab-events")).toBeInTheDocument();
  });

  it("hides broker-wide tabs from a non-super-admin", async () => {
    setup({ superAdmin: false });

    await waitFor(() => expect(screen.getByTestId("nats-tab-events")).toBeInTheDocument());
    // /varz and /jsz are account-wide and cannot be scoped per tenant.
    expect(screen.queryByTestId("nats-tab-overview")).toBeNull();
    expect(screen.queryByTestId("nats-tab-streams")).toBeNull();
    expect(screen.queryByTestId("nats-tab-tenants")).toBeNull();
  });

  it("lands a non-super-admin straight on event history", async () => {
    setup({ superAdmin: false });

    await waitFor(() => expect(screen.getByTestId("nats-events")).toBeInTheDocument());
    expect(mockGetEvents).toHaveBeenCalled();
    expect(mockGetOverview).not.toHaveBeenCalled();
  });

  it("does not offer a tenant filter to a non-super-admin", async () => {
    setup({ superAdmin: false });

    await waitFor(() => expect(screen.getByTestId("nats-events")).toBeInTheDocument());
    expect(screen.queryByTestId("nats-tenant-filter")).toBeNull();
  });

  it("offers the tenant filter to a super-admin, defaulted to all tenants", async () => {
    setup();

    const eventsTab = screen.getByTestId("nats-tab-events");
    eventsTab.click();

    await waitFor(() => expect(screen.getByTestId("nats-tenant-filter")).toBeInTheDocument());
    // Defaults to all tenants: a super-admin whose global tenant selector has nothing
    // active would otherwise 400 with "an active tenant is required".
    expect(mockGetEvents).toHaveBeenCalledWith(
      expect.objectContaining({ allTenants: true, tenantId: undefined }),
    );
  });

  it("lists the tenants that have NATS activity, not a raw id list", async () => {
    setup();
    mockGetTenants.mockResolvedValue(TENANTS);

    screen.getByTestId("nats-tab-events").click();
    await waitFor(() => expect(screen.getByTestId("nats-tenant-filter")).toBeInTheDocument());

    const combobox = within(screen.getByTestId("nats-tenant-filter")).getByRole("combobox");
    fireEvent.mouseDown(combobox);

    expect(await screen.findByRole("option", { name: "acme" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "globex" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "All tenants" })).toBeInTheDocument();
  });

  it("switches to a single tenant when one is picked from the dropdown", async () => {
    setup();
    mockGetTenants.mockResolvedValue(TENANTS);

    screen.getByTestId("nats-tab-events").click();
    await waitFor(() => expect(screen.getByTestId("nats-tenant-filter")).toBeInTheDocument());

    const combobox = within(screen.getByTestId("nats-tenant-filter")).getByRole("combobox");
    fireEvent.mouseDown(combobox);
    fireEvent.click(await screen.findByRole("option", { name: "globex" }));

    await waitFor(() =>
      expect(mockGetEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ tenantId: "tenant-globex", allTenants: undefined }),
      ),
    );
  });

  it("returns to all tenants when that option is re-selected", async () => {
    setup();
    mockGetTenants.mockResolvedValue(TENANTS);

    screen.getByTestId("nats-tab-events").click();
    await waitFor(() => expect(screen.getByTestId("nats-tenant-filter")).toBeInTheDocument());

    const combobox = within(screen.getByTestId("nats-tenant-filter")).getByRole("combobox");
    fireEvent.mouseDown(combobox);
    fireEvent.click(await screen.findByRole("option", { name: "acme" }));
    await waitFor(() =>
      expect(mockGetEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ tenantId: "tenant-acme" }),
      ),
    );

    fireEvent.mouseDown(combobox);
    fireEvent.click(await screen.findByRole("option", { name: "All tenants" }));

    await waitFor(() =>
      expect(mockGetEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ allTenants: true, tenantId: undefined }),
      ),
    );
  });

  it("shows the health chip and server figures on overview", async () => {
    setup();

    await waitFor(() => expect(screen.getByTestId("nats-health-chip")).toBeInTheDocument());
    // t() is mocked to echo the key, and translate() falls back to English when a key is
    // missing, so the rendered label is the fallback text rather than the key.
    expect(screen.getByTestId("nats-health-chip")).toHaveTextContent("Healthy");
  });

  it("hides the Grafana link when no URL is configured", async () => {
    setup();

    await waitFor(() => expect(screen.getByTestId("nats-overview")).toBeInTheDocument());
    expect(screen.queryByTestId("nats-grafana-link")).toBeNull();
  });

  it("shows the Grafana link when a URL is configured", async () => {
    setup({ grafanaUrl: "http://localhost:6868" });

    await waitFor(() => expect(screen.getByTestId("nats-grafana-link")).toBeInTheDocument());
  });

  it("renders an error rather than a blank panel when the broker is unreachable", async () => {
    mockIsSuperAdmin.mockReturnValue(true);
    mockIsLoggedIn.mockReturnValue(true);
    mockUseConfig.mockReturnValue({
      NATS_MONITORING_ENABLED: true,
      NATS_MESSAGE_INSPECTION_ENABLED: false,
      GRAFANA_URL: "",
    });
    mockGetOverview.mockRejectedValue({
      error_code: "nats_monitoring_unavailable",
      message: "broker unreachable",
    });

    render(
      <MemoryRouter initialEntries={["/monitoring/nats"]}>
        <Routes>
          <Route path="/monitoring/nats" element={<MonitoringNatsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("nats-overview-error")).toBeInTheDocument(),
    );
  });

  it("exposes a manual refresh and leaves auto-refresh off by default", async () => {
    setup();

    await waitFor(() => expect(screen.getByTestId("nats-refresh-button")).toBeInTheDocument());
    // MUI puts the test id on the Switch wrapper, so reach the real checkbox inside it.
    const toggle = screen
      .getByTestId("nats-auto-refresh-toggle")
      .querySelector("input") as HTMLInputElement;
    expect(toggle.checked).toBe(false);
  });
});

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  activeTenantFromContext,
  capabilitiesFromContext,
  tenantRegistryFromContext,
  type SessionFixtureContext,
} from '@/components/session/testSupport';
import { ApiError } from '@/lib/api';

const mockUseCapabilities = vi.fn();
const mockUseTenantRegistry = vi.fn();
const mockUseActiveTenant = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => mockUseTenantRegistry(),
}));

const api = {
  fetchNatsOverview: vi.fn(),
  fetchNatsStreams: vi.fn(),
  fetchNatsTenants: vi.fn(),
  fetchNatsEvents: vi.fn(),
  fetchNatsEventSummary: vi.fn(),
  fetchNatsEventPayload: vi.fn(),
};
vi.mock('@/lib/natsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/natsApi')>('@/lib/natsApi');
  return {
    ...actual,
    fetchNatsOverview: () => api.fetchNatsOverview(),
    fetchNatsStreams: () => api.fetchNatsStreams(),
    fetchNatsTenants: () => api.fetchNatsTenants(),
    fetchNatsEvents: (...args: unknown[]) => api.fetchNatsEvents(...args),
    fetchNatsEventSummary: (...args: unknown[]) => api.fetchNatsEventSummary(...args),
    fetchNatsEventPayload: (...args: unknown[]) => api.fetchNatsEventPayload(...args),
  };
});

import NatsMonitorPage from './NatsMonitorPage';
import { formatBytes } from './natsShared';

const consumer = (name: string, pending: number) => ({
  name,
  filterSubject: null,
  pending,
  unacked: 0,
  streamLag: 0,
  redelivered: 0,
  waiting: 1,
  deliveredStreamSeq: 100,
  ackFloorStreamSeq: 100,
  lastActive: null,
});

const stream = (name: string, extra: Record<string, unknown> = {}) => ({
  name,
  subjects: [`${name.toLowerCase()}.>`],
  isInternal: false,
  messages: 54,
  bytes: 2048,
  firstSeq: 1,
  lastSeq: 54,
  numSubjects: 5,
  consumerCount: 1,
  consumers: [] as ReturnType<typeof consumer>[],
  ...extra,
});

const JETSTREAM = {
  memoryBytes: 0,
  storageBytes: 12_776_000_000,
  totalStreams: 3,
  totalConsumers: 3,
  totalMessages: 118,
  totalBytes: 57_651,
};

const OVERVIEW = { healthy: true };

const STREAMS = {
  streams: [
    stream('M8FLOW_EVENTS', {
      consumerCount: 2,
      consumers: [consumer('m8flow-engine-consumer', 0), consumer('legacy-export', 4021)],
    }),
    stream('M8FLOW_NOTIFICATIONS', {
      consumers: [consumer('m8flow-notification-worker', 3)],
      config: {
        retention: 'workqueue',
        storage: 'memory',
        replicas: 3,
        maxAgeSeconds: 7 * 86400,
        maxMsgs: 10000,
        maxBytes: -1,
        maxMsgSize: -1,
        maxMsgsPerSubject: -1,
        maxConsumers: -1,
        discard: 'new',
        duplicateWindowSeconds: 120,
        compression: 'none',
        sealed: false,
        denyDelete: true,
        denyPurge: false,
      },
    }),
    stream('KV_config', { isInternal: true, consumerCount: 0 }),
  ],
  totals: { streams: 2, consumers: 3, messages: 110, bytes: 0, pending: 4024, unacked: 0, redelivered: 0, internalStreams: 1 },
  jetstream: JETSTREAM,
};

const EVENT = {
  id: 1,
  tenantId: 't-1',
  eventId: 'evt-1',
  worker: 'consumer',
  streamName: 'M8FLOW_EVENTS',
  streamSeq: 9,
  processIdentifier: 'group-a/flow-a1',
  username: 'admin',
  outcome: 'model_not_found',
  duplicateCount: 0,
  errorMessage: "Process model 'group-a/flow-a1' not found",
  processInstanceId: null,
  queuedAtInSeconds: 1_786_000_000,
  completedAtInSeconds: 1_786_000_001,
};

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

const SUPER_ADMIN: SessionFixtureContext = {
  scopedTenantId: null,
  selectedTenantId: null,
  isSuperAdmin: true,
  canReadNatsMonitoring: true,
  canReadNatsEvents: true,
};
const TENANT_ADMIN: SessionFixtureContext = {
  scopedTenantId: 't-1',
  selectedTenantId: 't-1',
  isSuperAdmin: false,
  canReadNatsEvents: true,
};
const NO_ACCESS: SessionFixtureContext = { scopedTenantId: 't-1', selectedTenantId: 't-1', isSuperAdmin: false };

function renderPage(path = '/system/nats', ctx: SessionFixtureContext = SUPER_ADMIN) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(ctx));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(ctx));
  mockUseTenantRegistry.mockReturnValue(tenantRegistryFromContext({ ...ctx, tenants: [{ id: 't-1', name: 'm8flow' }] }));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/system/nats"
          element={
            <>
              <NatsMonitorPage />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  api.fetchNatsOverview.mockResolvedValue(OVERVIEW);
  api.fetchNatsStreams.mockResolvedValue(STREAMS);
  api.fetchNatsTenants.mockResolvedValue([
    { tenantId: 't-1', tenantSlug: 'm8flow', queued: 0, instantiated: 7, failed: 3, total: 10, lastActivityInSeconds: 0 },
    { tenantId: null, tenantSlug: '(unattributed)', queued: 0, instantiated: 0, failed: 1, total: 1, lastActivityInSeconds: 0 },
  ]);
  api.fetchNatsEvents.mockResolvedValue({
    messageInspectionEnabled: true,
    results: [EVENT],
    pagination: { page: 1, perPage: 25, total: 1, pages: 1 },
  });
  api.fetchNatsEventSummary.mockResolvedValue({ total: 11, queued: 0, instantiated: 8, failed: 3, duplicateDeliveries: 0 });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('NatsMonitorPage', () => {
  it('shows the headline stats above the tabs and opens on Streams & consumers', async () => {
    renderPage();

    expect(await screen.findByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('4,024')).toBeInTheDocument();
    await vi.waitFor(() => expect(screen.getByTitle(/never became a process instance/)).toHaveTextContent('Failed3'));
    expect(api.fetchNatsEventSummary).toHaveBeenCalledWith({ tenantId: null, allTenants: true });
    expect(screen.getByText('11.9 GB')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Overview' })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Streams & consumers' })).toHaveAttribute('aria-selected', 'true');
  });

  it('polls at the chosen auto-refresh interval and stops when set to Off', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderPage();
      await screen.findByText('Connected');
      expect(api.fetchNatsOverview).toHaveBeenCalledTimes(1);

      await user.click(screen.getByRole('combobox', { name: 'Auto refresh' }));
      await user.click(await screen.findByRole('option', { name: 'Every 5 seconds' }));
      await vi.advanceTimersByTimeAsync(5_000);
      expect(api.fetchNatsOverview).toHaveBeenCalledTimes(2);

      await user.click(screen.getByRole('combobox', { name: 'Auto refresh' }));
      await user.click(await screen.findByRole('option', { name: 'Off' }));
      await vi.advanceTimersByTimeAsync(30_000);
      expect(api.fetchNatsOverview).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('lists every stream with its consumers in one table, internal streams on toggle', async () => {
    renderPage('/system/nats?tab=streams');

    // Consumers sit in the streams table itself, for every stream at once.
    const [table] = await screen.findAllByRole('table');
    expect(within(table).getByText('legacy-export')).toBeInTheDocument();
    expect(within(table).getByText('m8flow-notification-worker')).toBeInTheDocument();
    expect(within(table).getByText('3 pending · 100 acked')).toBeInTheDocument();
    expect(within(table).getByText('Lagging')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Consumers', level: 2 })).not.toBeInTheDocument();
    expect(screen.queryByText('KV_config')).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('Show internal'));
    expect(screen.getByText('KV_config')).toBeInTheDocument();
  });

  it('shows full consumer metrics for the clicked stream in its details', async () => {
    renderPage('/system/nats?tab=streams');
    await userEvent.click(await screen.findByText('M8FLOW_NOTIFICATIONS'));

    const details = screen.getByText('Stream details').closest('[data-slot="card"]') as HTMLElement;
    expect(within(details).getByText('Stream lag')).toBeInTheDocument();
    expect(within(details).getByText('Delivered seq')).toBeInTheDocument();
    expect(within(details).getByText('m8flow-notification-worker')).toBeInTheDocument();
    expect(within(details).queryByText('legacy-export')).not.toBeInTheDocument();
  });

  it('shows details for the clicked stream', async () => {
    renderPage('/system/nats?tab=streams');
    await userEvent.click(await screen.findByText('M8FLOW_NOTIFICATIONS'));

    const details = screen.getByText('Stream details').closest('[data-slot="card"]') as HTMLElement;
    const value = (label: string) => within(details).getByText(label).nextElementSibling?.textContent;
    expect(within(details).getAllByText('M8FLOW_NOTIFICATIONS').length).toBeGreaterThan(0);
    expect(value('Retention')).toBe('workqueue');
    expect(value('Storage')).toBe('memory');
    expect(value('Replicas')).toBe('3');
    expect(value('Max age')).toBe('7d');
    expect(value('Max messages')).toBe('10,000');
    expect(value('Max size')).toBe('Unlimited');
    expect(value('When full')).toBe('Discard new');
    expect(value('Duplicate window')).toBe('2m');
    expect(value('Protections')).toBe('Deny delete');
    expect(value('Sequence range')).toBe('1–54');
  });

  it('omits the payload action when inspection is disabled', async () => {
    api.fetchNatsEvents.mockResolvedValue({
      messageInspectionEnabled: false,
      results: [EVENT],
      pagination: { page: 1, perPage: 25, total: 1, pages: 1 },
    });
    renderPage('/system/nats?tab=events');

    await userEvent.click(await screen.findByText('Process not found'));
    expect(screen.queryByRole('button', { name: 'Show message payload' })).not.toBeInTheDocument();
    expect(screen.getByText(/payload inspection is disabled/i)).toBeInTheDocument();
    expect(api.fetchNatsEventPayload).not.toHaveBeenCalled();
  });

  it('opens event history filtered to a tenant from the Tenants tab', async () => {
    renderPage('/system/nats?tab=tenants');

    // Unattributed rows have no tenant to filter on.
    expect(await screen.findAllByRole('button', { name: 'View events' })).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: 'View events' }));

    expect(screen.getByTestId('location')).toHaveTextContent('tab=events&tenant=t-1');
    await vi.waitFor(() =>
      expect(api.fetchNatsEvents).toHaveBeenCalledWith(expect.objectContaining({ tenantId: 't-1', page: 1 })),
    );
  });

  it('expands an event to show its failure, details and redacted payload', async () => {
    api.fetchNatsEventPayload.mockResolvedValue({
      ...EVENT,
      payload: {
        seq: 9,
        subject: 'm8flow.events.m8flow.trigger',
        time: null,
        sizeBytes: 410,
        payload: '{"id":"evt-1","api_key":"[redacted]"}',
        encoding: 'utf-8',
        truncated: false,
      },
    });
    renderPage('/system/nats?tab=events');

    const row = await screen.findByText('Process not found');
    expect(screen.queryByText('Duplicate deliveries')).not.toBeInTheDocument();
    await userEvent.click(row);

    expect(screen.getByRole('alert')).toHaveTextContent("Process model 'group-a/flow-a1' not found");
    await userEvent.click(screen.getByRole('button', { name: 'Show message payload' }));

    expect(api.fetchNatsEventPayload).toHaveBeenCalledWith('evt-1', { tenantId: 't-1', allTenants: true });
    expect(await screen.findByText(/"api_key": "\[redacted\]"/)).toBeInTheDocument();
    expect(screen.getByText(/410 bytes/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('button', { name: 'Show message payload' })).toBeInTheDocument();
  });

  it('shows which stream each event came from and filters by stream', async () => {
    api.fetchNatsEvents.mockResolvedValue({
      messageInspectionEnabled: true,
      results: [
        EVENT,
        {
          ...EVENT,
          id: 2,
          eventId: 'extform-7-task-1',
          worker: 'notification_worker',
          streamName: 'M8FLOW_NOTIFICATIONS',
          processIdentifier: null,
          username: null,
          outcome: 'instantiated',
          errorMessage: null,
          processInstanceId: 7,
        },
      ],
      pagination: { page: 1, perPage: 25, total: 2, pages: 1 },
    });
    renderPage('/system/nats?tab=events');

    expect(await screen.findByText('M8FLOW_NOTIFICATIONS')).toBeInTheDocument();
    expect(screen.getByText('M8FLOW_EVENTS')).toBeInTheDocument();
    // A delivered notification is "Sent", not "Started".
    expect(screen.getByText('Sent')).toBeInTheDocument();
    expect(api.fetchNatsEvents).toHaveBeenLastCalledWith(expect.objectContaining({ worker: '' }));

    await userEvent.click(screen.getByRole('combobox', { name: 'Stream' }));
    await userEvent.click(await screen.findByRole('option', { name: 'Notifications' }));

    expect(screen.getByTestId('location')).toHaveTextContent('source=notification_worker');
    await vi.waitFor(() =>
      expect(api.fetchNatsEvents).toHaveBeenLastCalledWith(expect.objectContaining({ worker: 'notification_worker' })),
    );
  });

  it('queries all tenants by default and applies the failures-only filter', async () => {
    renderPage('/system/nats?tab=events');
    await screen.findByText('Process not found');
    expect(api.fetchNatsEvents).toHaveBeenLastCalledWith(
      expect.objectContaining({ tenantId: null, allTenants: true, failuresOnly: false }),
    );

    await userEvent.click(screen.getByText('Failures only'));

    await vi.waitFor(() =>
      expect(api.fetchNatsEvents).toHaveBeenLastCalledWith(expect.objectContaining({ failuresOnly: true })),
    );
  });

  it('drops the last broker snapshot when NATS goes down on refresh', async () => {
    renderPage('/system/nats?tab=streams');
    expect(await screen.findByText('11.9 GB')).toBeInTheDocument();

    api.fetchNatsOverview.mockRejectedValue(
      new ApiError('/v1.0/m8flow/nats/overview', 503, 'GET', 'The NATS server is not reachable. It may be stopped.'),
    );
    await userEvent.click(screen.getByRole('button', { name: /refresh/i }));

    expect(await screen.findByText('Disconnected')).toBeInTheDocument();
    expect(screen.queryByText('11.9 GB')).not.toBeInTheDocument();
    expect(screen.queryByText('legacy-export')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('NATS unavailable. The NATS server is not reachable.');
  });

  it('shows Disconnected with the error when the broker is unreachable', async () => {
    api.fetchNatsOverview.mockRejectedValue(new ApiError('/v1.0/m8flow/nats/overview', 503));
    renderPage();

    expect(await screen.findByText('Disconnected')).toBeInTheDocument();
    expect(screen.getAllByRole('alert')[0]).toHaveTextContent(/NATS unavailable\. The NATS server is not reachable/);
    // No stale broker numbers shown as live; the Streams tab explains why it is empty.
    expect(screen.queryByText('11.9 GB')).not.toBeInTheDocument();
    expect(screen.getByText(/can.t be shown until it is reachable/)).toBeInTheDocument();
  });

  it('shows a tenant-admin only their own event history', async () => {
    renderPage('/system/nats', TENANT_ADMIN);

    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Event history']);
    // Broker-wide state is super-admin only: no badge, no stat card, no broker calls.
    expect(await screen.findByText('Process not found')).toBeInTheDocument();
    expect(screen.queryByText('Connected')).not.toBeInTheDocument();
    expect(api.fetchNatsOverview).not.toHaveBeenCalled();
    expect(api.fetchNatsStreams).not.toHaveBeenCalled();
    // No cross-tenant filter, and no scope sent -- the backend pins them to their tenant.
    expect(screen.queryByRole('combobox', { name: 'Tenant' })).not.toBeInTheDocument();
    expect(api.fetchNatsEvents).toHaveBeenLastCalledWith(expect.objectContaining({ tenantId: null, allTenants: false }));
  });

  it('does not call the API without the backend read permission', () => {
    renderPage('/system/nats', NO_ACCESS);

    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(within(document.body).queryByRole('tablist')).not.toBeInTheDocument();
    expect(api.fetchNatsOverview).not.toHaveBeenCalled();
  });

  it('formats bytes', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1229)).toBe('1.2 KB');
  });
});

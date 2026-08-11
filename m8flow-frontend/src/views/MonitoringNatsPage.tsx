import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Box,
  Button,
  FormControlLabel,
  Stack,
  Switch,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import NatsEventsPanel from "../components/nats/NatsEventsPanel";
import NatsOverviewPanel from "../components/nats/NatsOverviewPanel";
import NatsStreamsPanel from "../components/nats/NatsStreamsPanel";
import NatsTenantsPanel from "../components/nats/NatsTenantsPanel";
import UserService from "../services/UserService";
import { useConfig } from "../utils/useConfig";

const AUTO_REFRESH_INTERVAL_MS = 10_000;

/**
 * NATS monitoring dashboard.
 *
 * Replaces the third-party NUI dashboard this page used to embed in an iframe, which could
 * not be extended with the metrics we need, carried no m8flow authentication or tenant
 * scoping, and could not be styled or deep-linked.
 *
 * The tab split mirrors what the backend can honestly scope. Broker-wide state (/varz,
 * /jsz) is reported per account rather than per tenant, so Overview, Streams and Tenants
 * are super-admin only. Event history comes from the audit trail, which carries a tenant
 * per row, so a tenant-admin sees their own — and reaching this page at all is gated on the
 * `read-nats-events` permission rather than on a super-admin flag.
 */
export default function MonitoringNatsPage() {
  const { t } = useTranslation();
  const translate = useCallback(
    (key: string, fallback: string) => {
      const translated = t(key);
      return translated === key ? fallback : translated;
    },
    [t],
  );

  const { NATS_MONITORING_ENABLED, NATS_MESSAGE_INSPECTION_ENABLED, GRAFANA_URL } =
    useConfig();

  const isSuperAdmin = UserService.isSuperAdmin();

  const [tabIndex, setTabIndex] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [tenantFilter, setTenantFilter] = useState<string | null>(null);

  const tabs = useMemo(() => {
    const items: { key: string; label: string }[] = [];
    if (isSuperAdmin) {
      items.push({ key: "overview", label: translate("nats_tab_overview", "Overview") });
      items.push({
        key: "streams",
        label: translate("nats_tab_streams", "Streams & consumers"),
      });
      items.push({ key: "tenants", label: translate("nats_tab_tenants", "Tenants") });
    }
    items.push({ key: "events", label: translate("nats_tab_events", "Event history") });
    return items;
  }, [isSuperAdmin, translate]);

  const activeTab = tabs[Math.min(tabIndex, tabs.length - 1)]?.key ?? "events";

  // Opt-in only, and paused while the tab is hidden so a backgrounded dashboard does not
  // keep polling the broker.
  useEffect(() => {
    if (!autoRefresh) {
      return undefined;
    }
    const timer = setInterval(() => {
      if (typeof document === "undefined" || !document.hidden) {
        setRefreshKey((key) => key + 1);
      }
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [autoRefresh]);

  if (!NATS_MONITORING_ENABLED) {
    return (
      <Box sx={{ p: 3 }} data-testid="nats-monitoring-not-configured">
        <Typography variant="h5" component="h1" gutterBottom>
          {t("nats_monitoring")}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {translate(
            "nats_monitoring_not_configured",
            "NATS monitoring is not enabled on this deployment. Set M8FLOW_NATS_MONITORING_ENABLED=true to turn it on.",
          )}
        </Typography>
      </Box>
    );
  }

  // Belt-and-suspenders, not the actual gate: the route element (ContainerForExtensions.tsx)
  // already checks the read-nats-events permission before this component ever renders. This
  // just catches an unauthenticated session directly, since isLoggedIn() has no notion of
  // permissions -- a super-admin is exempted here only to match that upstream check's shape.
  if (!isSuperAdmin && !UserService.isLoggedIn()) {
    return <Navigate to="/" replace />;
  }

  const goToTenantEvents = (tenantId: string | null) => {
    setTenantFilter(tenantId);
    const eventsIndex = tabs.findIndex((tab) => tab.key === "events");
    if (eventsIndex >= 0) {
      setTabIndex(eventsIndex);
    }
  };

  return (
    <Box sx={{ p: 3 }} data-testid="nats-monitoring-page">
      <Stack
        direction="row"
        alignItems="flex-start"
        justifyContent="space-between"
        spacing={2}
        sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h5" component="h1">
            {t("nats_monitoring")}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t("nats_monitoring_description")}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                data-testid="nats-auto-refresh-toggle"
              />
            }
            label={translate("nats_auto_refresh", "Auto refresh")}
          />
          <Button
            variant="outlined"
            size="small"
            startIcon={<RefreshIcon />}
            onClick={() => setRefreshKey((key) => key + 1)}
            data-testid="nats-refresh-button"
          >
            {translate("nats_refresh", "Refresh")}
          </Button>
        </Stack>
      </Stack>

      <Tabs
        value={Math.min(tabIndex, tabs.length - 1)}
        onChange={(_e, next) => setTabIndex(next)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ borderBottom: "1px solid", borderColor: "divider", mb: 2 }}
      >
        {tabs.map((tab) => (
          <Tab key={tab.key} label={tab.label} data-testid={`nats-tab-${tab.key}`} />
        ))}
      </Tabs>

      {activeTab === "overview" && (
        <NatsOverviewPanel
          translate={translate}
          refreshKey={refreshKey}
          grafanaUrl={GRAFANA_URL}
        />
      )}
      {activeTab === "streams" && (
        <NatsStreamsPanel translate={translate} refreshKey={refreshKey} />
      )}
      {activeTab === "tenants" && (
        <NatsTenantsPanel
          translate={translate}
          refreshKey={refreshKey}
          onInspectTenant={goToTenantEvents}
        />
      )}
      {activeTab === "events" && (
        <NatsEventsPanel
          translate={translate}
          refreshKey={refreshKey}
          canCrossTenant={isSuperAdmin}
          // Not gated on isSuperAdmin: only tenant-admin and super-admin can reach event
          // rows at all (read-nats-events is restricted to those two groups), and the
          // backend scopes a tenant-admin's payload view to their own tenant's events --
          // same reasoning as event history itself being open to tenant-admins.
          canInspectPayloads={Boolean(NATS_MESSAGE_INSPECTION_ENABLED)}
          initialTenantId={tenantFilter}
        />
      )}
    </Box>
  );
}

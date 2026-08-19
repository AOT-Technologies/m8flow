import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import NatsMonitoringService, {
  NatsOverview,
} from "../../services/NatsMonitoringService";
import {
  Translate,
  formatBytes,
  formatNumber,
  formatPercent,
  loadErrorMessage,
} from "./natsFormat";

interface OwnProps {
  translate: Translate;
  refreshKey: number;
  grafanaUrl?: string;
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, minWidth: 160, flex: "1 1 160px" }}>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="h6" component="div" sx={{ wordBreak: "break-word" }}>
        {value}
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.secondary">
          {hint}
        </Typography>
      )}
    </Paper>
  );
}

export default function NatsOverviewPanel({
  translate,
  refreshKey,
  grafanaUrl,
}: OwnProps) {
  const [overview, setOverview] = useState<NatsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    NatsMonitoringService.getOverview()
      .then((result) => {
        setOverview(result);
        setError("");
      })
      .catch((e) => setError(loadErrorMessage(e, translate)))
      .finally(() => setLoading(false));
    // translate is stable for the lifetime of the page; excluded to avoid refetch churn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load, refreshKey]);

  if (loading && !overview) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress data-testid="nats-overview-loading" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="warning" data-testid="nats-overview-error">
        {error}
      </Alert>
    );
  }

  if (!overview) {
    return null;
  }

  return (
    <Box data-testid="nats-overview">
      <Stack
        direction="row"
        spacing={2}
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            label={
              overview.healthy
                ? translate("nats_healthy", "Healthy")
                : translate("nats_unhealthy", "Unhealthy")
            }
            color={overview.healthy ? "success" : "error"}
            size="small"
            data-testid="nats-health-chip"
          />
          <Typography variant="body2" color="text.secondary">
            {overview.version ? `NATS ${overview.version}` : ""}
            {overview.uptime ? ` · ${translate("nats_uptime", "up")} ${overview.uptime}` : ""}
          </Typography>
        </Stack>
        {grafanaUrl && (
          <Button
            variant="outlined"
            size="small"
            startIcon={<OpenInNewIcon />}
            onClick={() => window.open(grafanaUrl, "_blank", "noopener,noreferrer")}
            data-testid="nats-grafana-link"
          >
            {translate("nats_view_trends_in_grafana", "View trends in Grafana")}
          </Button>
        )}
      </Stack>

      {overview.slowConsumers > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="nats-slow-consumers-alert">
          {translate(
            "nats_slow_consumers_warning",
            "The server reports slow consumers, which means messages are being dropped for connections that cannot keep up.",
          )}
        </Alert>
      )}

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {translate("nats_server", "Server")}
      </Typography>
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", gap: 2, mb: 3 }}>
        <Stat
          label={translate("nats_connections", "Connections")}
          value={formatNumber(overview.connections)}
          hint={`${formatNumber(overview.totalConnections)} ${translate("nats_total", "total")}`}
        />
        <Stat
          label={translate("nats_subscriptions", "Subscriptions")}
          value={formatNumber(overview.subscriptions)}
        />
        <Stat
          label={translate("nats_messages_in", "Messages in")}
          value={formatNumber(overview.inMsgs)}
          hint={formatBytes(overview.inBytes)}
        />
        <Stat
          label={translate("nats_messages_out", "Messages out")}
          value={formatNumber(overview.outMsgs)}
          hint={formatBytes(overview.outBytes)}
        />
        <Stat
          label={translate("nats_slow_consumers", "Slow consumers")}
          value={formatNumber(overview.slowConsumers)}
        />
        <Stat
          label={translate("nats_memory", "Memory")}
          value={formatBytes(overview.memoryBytes)}
          hint={`${formatPercent(overview.cpuPercent)}% ${translate("nats_cpu", "CPU")}`}
        />
      </Stack>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {translate("nats_jetstream", "JetStream")}
      </Typography>
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", gap: 2 }}>
        <Stat
          label={translate("nats_streams", "Streams")}
          value={formatNumber(overview.jetstream.totalStreams)}
        />
        <Stat
          label={translate("nats_consumers", "Consumers")}
          value={formatNumber(overview.jetstream.totalConsumers)}
        />
        <Stat
          label={translate("nats_stored_messages", "Stored messages")}
          value={formatNumber(overview.jetstream.totalMessages)}
          hint={formatBytes(overview.jetstream.totalBytes)}
        />
        <Stat
          label={translate("nats_storage", "Storage")}
          value={formatBytes(overview.jetstream.storageBytes)}
          hint={`${formatBytes(overview.jetstream.memoryBytes)} ${translate("nats_in_memory", "in memory")}`}
        />
      </Stack>
    </Box>
  );
}

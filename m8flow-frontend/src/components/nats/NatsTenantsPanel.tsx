import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import NatsMonitoringService, {
  NatsTenantEventCounts,
} from "../../services/NatsMonitoringService";
import {
  Translate,
  backlogColor,
  formatAge,
  formatNumber,
  loadErrorMessage,
} from "./natsFormat";

interface OwnProps {
  translate: Translate;
  refreshKey: number;
  /** Jump to the event history filtered to one tenant. */
  onInspectTenant: (tenantId: string | null) => void;
}

export default function NatsTenantsPanel({
  translate,
  refreshKey,
  onInspectTenant,
}: OwnProps) {
  const [rows, setRows] = useState<NatsTenantEventCounts[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    NatsMonitoringService.getTenants()
      .then((result) => {
        setRows(result);
        setError("");
      })
      .catch((e) => setError(loadErrorMessage(e, translate)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load, refreshKey]);

  if (loading && rows.length === 0) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress data-testid="nats-tenants-loading" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="warning" data-testid="nats-tenants-error">
        {error}
      </Alert>
    );
  }

  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="nats-tenants-empty">
        {translate(
          "nats_no_tenant_events",
          "No events have been processed yet. Trigger a workflow through the event API and it will appear here.",
        )}
      </Typography>
    );
  }

  return (
    <Box data-testid="nats-tenants">
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {translate(
          "nats_tenants_explainer",
          "Per-tenant backlog comes from the event audit trail: JetStream reports pending messages per consumer, and one consumer serves every tenant, so the broker cannot break it down this way.",
        )}
      </Typography>

      <TableContainer sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{translate("nats_tenant", "Tenant")}</TableCell>
              <TableCell align="right">{translate("nats_queued", "Queued")}</TableCell>
              <TableCell align="right">{translate("nats_started", "Started")}</TableCell>
              <TableCell align="right">{translate("nats_failed", "Failed")}</TableCell>
              <TableCell align="right">{translate("nats_total", "Total")}</TableCell>
              <TableCell align="right">{translate("nats_last_activity", "Last activity")}</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => {
              const unattributed = row.tenantId === null;
              return (
                <TableRow
                  key={row.tenantId ?? "unattributed"}
                  data-testid={`nats-tenant-${row.tenantId ?? "unattributed"}`}
                >
                  <TableCell>
                    {unattributed ? (
                      <Tooltip
                        title={translate(
                          "nats_unattributed_hint",
                          "Messages whose subject was malformed, so no tenant could be determined. Shown here rather than dropped.",
                        )}
                      >
                        <Chip
                          size="small"
                          variant="outlined"
                          label={translate("nats_unattributed", "unattributed")}
                        />
                      </Tooltip>
                    ) : (
                      <Typography variant="body2">{row.tenantSlug ?? row.tenantId}</Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Chip
                      size="small"
                      label={formatNumber(row.queued)}
                      color={backlogColor(row.queued)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatNumber(row.instantiated)}</TableCell>
                  <TableCell align="right">
                    <Chip
                      size="small"
                      variant={row.failed ? "filled" : "outlined"}
                      color={row.failed ? "error" : "success"}
                      label={formatNumber(row.failed)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatNumber(row.total)}</TableCell>
                  <TableCell align="right">
                    {formatAge(row.lastActivityInSeconds, translate)}
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      onClick={() => onInspectTenant(row.tenantId)}
                      data-testid={`nats-inspect-${row.tenantId ?? "unattributed"}`}
                    >
                      {translate("nats_view_events", "View events")}
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

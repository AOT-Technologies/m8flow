import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Collapse,
  FormControlLabel,
  IconButton,
  Link,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import NatsMonitoringService, {
  NATS_EVENT_OUTCOMES,
  NatsEventRecord,
  NatsEventSummary,
  NatsTenantEventCounts,
} from "../../services/NatsMonitoringService";
import {
  Translate,
  formatEpochSeconds,
  formatNumber,
  loadErrorMessage,
  outcomeColor,
  outcomeLabel,
} from "./natsFormat";

interface OwnProps {
  translate: Translate;
  refreshKey: number;
  /** Super-admins may read across tenants; everyone else is pinned server-side. */
  canCrossTenant: boolean;
  /** Payload viewing needs both the env flag and super-admin, so it is offered narrowly. */
  canInspectPayloads: boolean;
  /** Set when arriving from the Tenants tab. */
  initialTenantId?: string | null;
}

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: "success" | "error" | "info" | "default";
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, minWidth: 130, flex: "1 1 130px" }}>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography
        variant="h6"
        component="div"
        color={
          color === "error"
            ? "error.main"
            : color === "success"
              ? "success.main"
              : "text.primary"
        }
      >
        {value}
      </Typography>
    </Paper>
  );
}

function EventDetail({
  event,
  translate,
  canInspectPayloads,
}: {
  event: NatsEventRecord;
  translate: Translate;
  canInspectPayloads: boolean;
}) {
  const [payload, setPayload] = useState<NatsEventRecord["payload"]>(undefined);
  const [payloadError, setPayloadError] = useState("");
  const [loadingPayload, setLoadingPayload] = useState(false);

  const loadPayload = () => {
    if (!event.eventId) {
      return;
    }
    setLoadingPayload(true);
    NatsMonitoringService.getEvent(event.eventId, { includePayload: true })
      .then((full) => {
        setPayload(full.payload ?? null);
        setPayloadError("");
      })
      .catch((e) => setPayloadError(loadErrorMessage(e, translate)))
      .finally(() => setLoadingPayload(false));
  };

  return (
    <Box sx={{ p: 2, bgcolor: "action.hover" }}>
      <Stack spacing={1}>
        {event.errorMessage && (
          <Alert severity="error" sx={{ whiteSpace: "pre-wrap" }}>
            {event.errorMessage}
          </Alert>
        )}
        <Typography variant="body2">
          <strong>{translate("nats_event_id", "Event id")}:</strong>{" "}
          <span style={{ fontFamily: "monospace" }}>{event.eventId ?? "—"}</span>
        </Typography>
        <Typography variant="body2">
          <strong>{translate("nats_worker", "Worker")}:</strong> {event.worker}
        </Typography>
        <Typography variant="body2">
          <strong>{translate("nats_queued_at", "Queued")}:</strong>{" "}
          {formatEpochSeconds(event.queuedAtInSeconds)}
        </Typography>
        <Typography variant="body2">
          <strong>{translate("nats_completed_at", "Completed")}:</strong>{" "}
          {formatEpochSeconds(event.completedAtInSeconds)}
        </Typography>
        {event.processInstanceId ? (
          <Typography variant="body2">
            <strong>{translate("nats_process_instance", "Process instance")}:</strong>{" "}
            <Link href={`/process-instances/${event.processInstanceId}`}>
              #{event.processInstanceId}
            </Link>
          </Typography>
        ) : null}
        {event.duplicateCount > 0 && (
          <Alert severity="info">
            {translate(
              "nats_duplicate_explainer",
              "This event was re-sent {{n}} more time(s) and suppressed by the dedup guard, which usually means a client is retrying a trigger it already delivered.",
            ).replace("{{n}}", String(event.duplicateCount))}
          </Alert>
        )}

        {canInspectPayloads && event.streamSeq ? (
          <Box>
            {payload === undefined ? (
              <Link
                component="button"
                type="button"
                onClick={loadPayload}
                data-testid={`nats-load-payload-${event.id}`}
              >
                {loadingPayload
                  ? translate("nats_loading_payload", "Loading payload…")
                  : translate("nats_show_payload", "Show message payload")}
              </Link>
            ) : payload === null ? (
              <Typography variant="body2" color="text.secondary">
                {translate(
                  "nats_payload_gone",
                  "The message is no longer in the stream, so its payload cannot be shown.",
                )}
              </Typography>
            ) : (
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  {payload.subject} · {formatNumber(payload.sizeBytes)}{" "}
                  {translate("nats_bytes", "bytes")}
                  {payload.encoding !== "utf-8" ? ` · ${payload.encoding}` : ""}
                  {payload.truncated
                    ? ` · ${translate("nats_preview_truncated", "preview truncated")}`
                    : ""}
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    mt: 0.5,
                    p: 1,
                    maxHeight: 240,
                    overflow: "auto",
                    bgcolor: "background.paper",
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    fontSize: "0.75rem",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                  }}
                >
                  {payload.payload}
                </Box>
              </Box>
            )}
            {payloadError && (
              <Typography variant="caption" color="error">
                {payloadError}
              </Typography>
            )}
          </Box>
        ) : null}
      </Stack>
    </Box>
  );
}

export default function NatsEventsPanel({
  translate,
  refreshKey,
  canCrossTenant,
  canInspectPayloads,
  initialTenantId,
}: OwnProps) {
  const [events, setEvents] = useState<NatsEventRecord[]>([]);
  const [summary, setSummary] = useState<NatsEventSummary | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [perPage, setPerPage] = useState(25);
  const [outcome, setOutcome] = useState("");
  const [failuresOnly, setFailuresOnly] = useState(false);
  const [processIdentifier, setProcessIdentifier] = useState("");
  const [eventId, setEventId] = useState("");
  // Defaults to "all tenants" for a super-admin who hasn't drilled in from a specific
  // tenant. Without this, a super-admin whose global tenant selector is set to "All
  // Tenants" has no active tenant to fall back to, and the request 400s with "an active
  // tenant is required" -- correct backend behavior, but a bad default here.
  const [allTenants, setAllTenants] = useState(() => canCrossTenant && !initialTenantId);
  const [tenantId, setTenantId] = useState<string | null>(initialTenantId ?? null);
  const [tenantOptions, setTenantOptions] = useState<NatsTenantEventCounts[]>([]);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const scope = {
    allTenants: canCrossTenant && allTenants ? true : undefined,
    tenantId: canCrossTenant && tenantId ? tenantId : undefined,
  };

  // Populates the tenant picker below. Sourced from the audit trail's own per-tenant
  // roll-up rather than a general tenant-listing endpoint, so the choices are exactly
  // "tenants with NATS activity" -- the only ones this filter can do anything useful with.
  useEffect(() => {
    if (!canCrossTenant) {
      return;
    }
    NatsMonitoringService.getTenants()
      .then((rows) => {
        // The null-tenant "(unattributed)" grouping (malformed-subject events) has no id
        // to filter by, so it is informational on the Tenants tab only, not selectable here.
        const withIds = rows.filter((row) => row.tenantId);
        withIds.sort((a, b) => (a.tenantSlug ?? "").localeCompare(b.tenantSlug ?? ""));
        setTenantOptions(withIds);
      })
      .catch(() => {
        // Non-fatal: the picker just stays empty and search-by-tenant-id via drill-through
        // still works. Not worth its own error banner on a page that already has one.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canCrossTenant, refreshKey]);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      NatsMonitoringService.getEvents({
        ...scope,
        outcome: outcome || undefined,
        failuresOnly: failuresOnly || undefined,
        processIdentifier: processIdentifier || undefined,
        eventId: eventId || undefined,
        page: page + 1,
        perPage,
      }),
      NatsMonitoringService.getEventSummary(scope),
    ])
      .then(([list, counts]) => {
        setEvents(list.results ?? []);
        setTotal(list.pagination?.total ?? 0);
        setSummary(counts);
        setError("");
      })
      .catch((e) => setError(loadErrorMessage(e, translate)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    outcome,
    failuresOnly,
    processIdentifier,
    eventId,
    page,
    perPage,
    allTenants,
    tenantId,
  ]);

  useEffect(load, [load, refreshKey]);

  return (
    <Box data-testid="nats-events">
      {summary && (
        <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", gap: 2, mb: 2 }}>
          <SummaryCard
            label={translate("nats_total", "Total")}
            value={formatNumber(summary.total)}
          />
          <SummaryCard
            label={translate("nats_started", "Started")}
            value={formatNumber(summary.instantiated)}
            color="success"
          />
          <SummaryCard
            label={translate("nats_failed", "Failed")}
            value={formatNumber(summary.failed)}
            color={summary.failed ? "error" : "default"}
          />
          <SummaryCard
            label={translate("nats_queued", "Queued")}
            value={formatNumber(summary.queued)}
          />
          <SummaryCard
            label={translate("nats_duplicate_deliveries", "Duplicate deliveries")}
            value={formatNumber(summary.duplicateDeliveries)}
          />
        </Stack>
      )}

      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", gap: 2, mb: 2 }}>
        <TextField
          select
          size="small"
          label={translate("nats_outcome", "Outcome")}
          value={outcome}
          onChange={(e) => {
            setOutcome(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 180 }}
          data-testid="nats-outcome-filter"
          // displayEmpty makes the "" MenuItem's text ("Any outcome") render instead of a
          // blank box, but the floating label doesn't know a value is showing and stays in
          // its resting position unless shrink is forced -- without it, the label and the
          // displayed text draw on top of each other.
          slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
        >
          <MenuItem value="">{translate("nats_any_outcome", "Any outcome")}</MenuItem>
          {NATS_EVENT_OUTCOMES.map((value) => (
            <MenuItem key={value} value={value}>
              {outcomeLabel(value, translate)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label={translate("nats_process", "Process")}
          value={processIdentifier}
          onChange={(e) => {
            setProcessIdentifier(e.target.value);
            setPage(0);
          }}
          data-testid="nats-process-filter"
        />
        <TextField
          size="small"
          label={translate("nats_event_id", "Event id")}
          value={eventId}
          onChange={(e) => {
            setEventId(e.target.value);
            setPage(0);
          }}
          data-testid="nats-event-id-filter"
        />
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={failuresOnly}
              onChange={(e) => {
                setFailuresOnly(e.target.checked);
                setPage(0);
              }}
              data-testid="nats-failures-only-toggle"
            />
          }
          label={translate("nats_failures_only", "Failures only")}
        />
        {canCrossTenant && (
          <TextField
            select
            size="small"
            label={translate("nats_tenant", "Tenant")}
            value={tenantId ?? ""}
            onChange={(e) => {
              const next = e.target.value;
              if (next === "") {
                setAllTenants(true);
                setTenantId(null);
              } else {
                setAllTenants(false);
                setTenantId(next);
              }
              setPage(0);
            }}
            sx={{ minWidth: 200 }}
            data-testid="nats-tenant-filter"
            slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
          >
            <MenuItem value="">{translate("nats_all_tenants", "All tenants")}</MenuItem>
            {tenantOptions.map((tenant) => (
              <MenuItem key={tenant.tenantId} value={tenant.tenantId ?? ""}>
                {tenant.tenantSlug ?? tenant.tenantId}
              </MenuItem>
            ))}
            {/* The tenant that brought us here via drill-through may have since dropped
                out of tenantOptions (e.g. no activity in a later refresh); keep it
                selectable so the filter chosen from the Tenants tab never silently resets. */}
            {tenantId && !tenantOptions.some((t) => t.tenantId === tenantId) && (
              <MenuItem value={tenantId}>{tenantId}</MenuItem>
            )}
          </TextField>
        )}
      </Stack>

      {error ? (
        <Alert severity="warning" data-testid="nats-events-error">
          {error}
        </Alert>
      ) : loading && events.length === 0 ? (
        <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
          <CircularProgress data-testid="nats-events-loading" />
        </Box>
      ) : events.length === 0 ? (
        <Typography variant="body2" color="text.secondary" data-testid="nats-events-empty">
          {translate("nats_no_events", "No events match these filters.")}
        </Typography>
      ) : (
        <>
          <TableContainer sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 48 }} />
                  <TableCell>{translate("nats_outcome", "Outcome")}</TableCell>
                  <TableCell>{translate("nats_process", "Process")}</TableCell>
                  <TableCell>{translate("nats_user", "User")}</TableCell>
                  <TableCell>{translate("nats_event_id", "Event id")}</TableCell>
                  <TableCell align="right">{translate("nats_instance", "Instance")}</TableCell>
                  <TableCell align="right">{translate("nats_queued_at", "Queued")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {events.map((event) => {
                  const isOpen = Boolean(expanded[event.id]);
                  return [
                    <TableRow key={event.id} data-testid={`nats-event-${event.id}`}>
                      <TableCell>
                        <IconButton
                          size="small"
                          onClick={() =>
                            setExpanded((prev) => ({ ...prev, [event.id]: !isOpen }))
                          }
                          aria-label={translate("nats_toggle_detail", "Toggle detail")}
                          data-testid={`nats-event-toggle-${event.id}`}
                        >
                          {isOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                        </IconButton>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <Chip
                            size="small"
                            label={outcomeLabel(event.outcome, translate)}
                            color={outcomeColor(event.outcome)}
                          />
                          {event.duplicateCount > 0 && (
                            <Tooltip
                              title={translate(
                                "nats_duplicate_count_hint",
                                "Extra deliveries suppressed by the dedup guard",
                              )}
                            >
                              <Chip
                                size="small"
                                variant="outlined"
                                label={`+${event.duplicateCount}`}
                              />
                            </Tooltip>
                          )}
                        </Stack>
                      </TableCell>
                      <TableCell>{event.processIdentifier ?? "—"}</TableCell>
                      <TableCell>{event.username ?? "—"}</TableCell>
                      <TableCell>
                        <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                          {event.eventId ?? "—"}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        {event.processInstanceId ? (
                          <Link href={`/process-instances/${event.processInstanceId}`}>
                            #{event.processInstanceId}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell align="right">
                        {formatEpochSeconds(event.queuedAtInSeconds)}
                      </TableCell>
                    </TableRow>,
                    <TableRow key={`${event.id}-detail`}>
                      <TableCell
                        colSpan={7}
                        sx={{ py: 0, borderBottom: isOpen ? undefined : "none" }}
                      >
                        <Collapse in={isOpen} unmountOnExit>
                          <EventDetail
                            event={event}
                            translate={translate}
                            canInspectPayloads={canInspectPayloads}
                          />
                        </Collapse>
                      </TableCell>
                    </TableRow>,
                  ];
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={total}
            page={page}
            onPageChange={(_e, next) => setPage(next)}
            rowsPerPage={perPage}
            onRowsPerPageChange={(e) => {
              setPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </>
      )}
    </Box>
  );
}

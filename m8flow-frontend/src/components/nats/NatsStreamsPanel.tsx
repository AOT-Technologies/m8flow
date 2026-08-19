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
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useState } from "react";
import NatsMonitoringService, {
  NatsStream,
  NatsStreamsResponse,
} from "../../services/NatsMonitoringService";
import {
  Translate,
  backlogColor,
  formatBytes,
  formatNumber,
  loadErrorMessage,
  redeliveryColor,
} from "./natsFormat";

interface OwnProps {
  translate: Translate;
  refreshKey: number;
}

function ConsumerRows({
  stream,
  translate,
}: {
  stream: NatsStream;
  translate: Translate;
}) {
  if (stream.consumers.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
        {translate("nats_no_consumers", "No consumers on this stream.")}
      </Typography>
    );
  }

  return (
    <Table size="small" sx={{ mb: 1 }}>
      <TableHead>
        <TableRow>
          <TableCell>{translate("nats_consumer", "Consumer")}</TableCell>
          <TableCell align="right">{translate("nats_pending", "Pending")}</TableCell>
          <TableCell align="right">{translate("nats_unacked", "Unacked")}</TableCell>
          <TableCell align="right">{translate("nats_stream_lag", "Stream lag")}</TableCell>
          <TableCell align="right">{translate("nats_redelivered", "Redelivered")}</TableCell>
          <TableCell align="right">{translate("nats_waiting", "Waiting")}</TableCell>
          <TableCell align="right">{translate("nats_delivered_seq", "Delivered seq")}</TableCell>
          <TableCell align="right">{translate("nats_ack_floor", "Ack floor")}</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {stream.consumers.map((consumer) => (
          <TableRow key={consumer.name} data-testid={`nats-consumer-${consumer.name}`}>
            <TableCell>
              <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                {consumer.name}
              </Typography>
              {consumer.filterSubject && (
                <Typography variant="caption" color="text.secondary">
                  {Array.isArray(consumer.filterSubject)
                    ? consumer.filterSubject.join(", ")
                    : consumer.filterSubject}
                </Typography>
              )}
            </TableCell>
            <TableCell align="right">
              <Chip
                size="small"
                label={formatNumber(consumer.pending)}
                color={backlogColor(consumer.pending)}
                data-testid={`nats-pending-${consumer.name}`}
              />
            </TableCell>
            <TableCell align="right">{formatNumber(consumer.unacked)}</TableCell>
            <TableCell align="right">
              <Tooltip
                title={
                  consumer.filterSubject
                    ? translate(
                        "nats_stream_lag_filtered_hint",
                        "This consumer filters by subject, so stream lag counts messages it will never receive. Pending is the real backlog.",
                      )
                    : translate(
                        "nats_stream_lag_hint",
                        "Sequence distance from the head of the stream.",
                      )
                }
              >
                <span>{formatNumber(consumer.streamLag)}</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right">
              <Chip
                size="small"
                variant={consumer.redelivered ? "filled" : "outlined"}
                label={formatNumber(consumer.redelivered)}
                color={redeliveryColor(consumer.redelivered)}
              />
            </TableCell>
            <TableCell align="right">{formatNumber(consumer.waiting)}</TableCell>
            <TableCell align="right">{formatNumber(consumer.deliveredStreamSeq)}</TableCell>
            <TableCell align="right">{formatNumber(consumer.ackFloorStreamSeq)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function NatsStreamsPanel({ translate, refreshKey }: OwnProps) {
  const [data, setData] = useState<NatsStreamsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showInternal, setShowInternal] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = useCallback(() => {
    setLoading(true);
    NatsMonitoringService.getStreams()
      .then((result) => {
        setData(result);
        setError("");
      })
      .catch((e) => setError(loadErrorMessage(e, translate)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(load, [load, refreshKey]);

  const visibleStreams = useMemo(() => {
    if (!data) {
      return [];
    }
    return showInternal ? data.streams : data.streams.filter((s) => !s.isInternal);
  }, [data, showInternal]);

  if (loading && !data) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress data-testid="nats-streams-loading" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="warning" data-testid="nats-streams-error">
        {error}
      </Alert>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <Box data-testid="nats-streams">
      <Stack
        direction="row"
        spacing={2}
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 2, flexWrap: "wrap", gap: 1 }}
      >
        <Typography variant="body2" color="text.secondary">
          {translate("nats_streams_summary", "{{streams}} streams · {{consumers}} consumers · {{pending}} pending")
            .replace("{{streams}}", formatNumber(data.totals.streams))
            .replace("{{consumers}}", formatNumber(data.totals.consumers))
            .replace("{{pending}}", formatNumber(data.totals.pending))}
        </Typography>
        {data.totals.internalStreams > 0 && (
          <Tooltip
            title={translate(
              "nats_internal_streams_hint",
              "JetStream backs KV buckets and object stores with ordinary streams (KV_/OBJ_ prefixed). They are m8flow plumbing rather than event traffic.",
            )}
          >
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={showInternal}
                  onChange={(e) => setShowInternal(e.target.checked)}
                  data-testid="nats-show-internal-toggle"
                />
              }
              label={translate("nats_show_internal_streams", "Show internal streams")}
            />
          </Tooltip>
        )}
      </Stack>

      {visibleStreams.length === 0 ? (
        <Typography variant="body2" color="text.secondary" data-testid="nats-streams-empty">
          {translate("nats_no_streams", "No streams exist yet. They are created when the first event is published.")}
        </Typography>
      ) : (
        <TableContainer sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 48 }} />
                <TableCell>{translate("nats_stream", "Stream")}</TableCell>
                <TableCell align="right">{translate("nats_messages", "Messages")}</TableCell>
                <TableCell align="right">{translate("nats_size", "Size")}</TableCell>
                <TableCell align="right">{translate("nats_sequence_range", "Sequence range")}</TableCell>
                <TableCell align="right">{translate("nats_subjects", "Subjects")}</TableCell>
                <TableCell align="right">{translate("nats_consumers", "Consumers")}</TableCell>
                <TableCell align="right">{translate("nats_pending", "Pending")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleStreams.map((stream) => {
                const key = stream.name ?? "";
                const isOpen = Boolean(expanded[key]);
                const pending = stream.consumers.reduce((sum, c) => sum + c.pending, 0);
                return [
                  <TableRow key={key} data-testid={`nats-stream-${key}`}>
                    <TableCell>
                      <IconButton
                        size="small"
                        onClick={() => setExpanded((prev) => ({ ...prev, [key]: !isOpen }))}
                        aria-label={translate("nats_toggle_consumers", "Toggle consumers")}
                        data-testid={`nats-stream-toggle-${key}`}
                      >
                        {isOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      </IconButton>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                          {stream.name}
                        </Typography>
                        {stream.isInternal && (
                          <Chip
                            size="small"
                            variant="outlined"
                            label={translate("nats_internal", "internal")}
                          />
                        )}
                      </Stack>
                      <Typography variant="caption" color="text.secondary">
                        {stream.subjects.join(", ")}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{formatNumber(stream.messages)}</TableCell>
                    <TableCell align="right">{formatBytes(stream.bytes)}</TableCell>
                    <TableCell align="right">
                      {formatNumber(stream.firstSeq)}–{formatNumber(stream.lastSeq)}
                    </TableCell>
                    <TableCell align="right">{formatNumber(stream.numSubjects)}</TableCell>
                    <TableCell align="right">{formatNumber(stream.consumerCount)}</TableCell>
                    <TableCell align="right">
                      <Chip size="small" label={formatNumber(pending)} color={backlogColor(pending)} />
                    </TableCell>
                  </TableRow>,
                  <TableRow key={`${key}-consumers`}>
                    <TableCell colSpan={8} sx={{ py: 0, borderBottom: isOpen ? undefined : "none" }}>
                      <Collapse in={isOpen} unmountOnExit>
                        <ConsumerRows stream={stream} translate={translate} />
                      </Collapse>
                    </TableCell>
                  </TableRow>,
                ];
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

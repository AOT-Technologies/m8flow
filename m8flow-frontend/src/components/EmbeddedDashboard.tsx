import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

interface OwnProps {
  title: string;
  src: string;
  description?: string;
  /** Milliseconds to wait for the iframe to load before surfacing the slow/blocked notice. */
  loadTimeoutMs?: number;
}

const DEFAULT_LOAD_TIMEOUT_MS = 12_000;

/**
 * Renders an external operations dashboard (e.g. Celery Flower, NATS NUI) embedded
 * in an iframe inside the m8flow app shell, with a consistent page header.
 *
 * These dashboards live on external, cross-origin URLs. When an embed is refused via
 * `X-Frame-Options` / CSP `frame-ancestors`, the browser does NOT fire the iframe
 * `onError` event (and same-origin policy prevents inspecting the frame's content),
 * so a blocked embed is effectively undetectable from JavaScript and simply renders
 * as a blank frame. We therefore degrade gracefully with two mechanisms:
 *  - a best-effort load timeout that catches never-loads (connection refused, 404,
 *    very slow hosts) and surfaces a non-blocking notice without unmounting the frame
 *    (a slow-but-valid dashboard still appears if it eventually loads);
 *  - an always-visible "Open in new tab" action in the header, which is the guaranteed
 *    fallback for the silent blocked-embed case we cannot detect.
 * The `onError` handler is kept for the rare genuine error events but is not relied upon.
 */
export default function EmbeddedDashboard({
  title,
  src,
  description,
  loadTimeoutMs = DEFAULT_LOAD_TIMEOUT_MS,
}: OwnProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [noticeDismissed, setNoticeDismissed] = useState(false);

  // Best-effort detection of a frame that never loads. Reset whenever the src changes.
  useEffect(() => {
    setLoading(true);
    setFailed(false);
    setTimedOut(false);
    setNoticeDismissed(false);

    const timer = setTimeout(() => setTimedOut(true), loadTimeoutMs);
    return () => clearTimeout(timer);
  }, [src, loadTimeoutMs]);

  const openInNewTab = (
    <Button
      variant="outlined"
      size="small"
      startIcon={<OpenInNewIcon />}
      onClick={() => window.open(src, "_blank", "noopener,noreferrer")}
      data-testid="embedded-dashboard-open-new-tab"
    >
      {t("open_in_new_tab")}
    </Button>
  );

  // Show the slow/blocked notice once the timeout fires while still loading, unless dismissed.
  const showSlowNotice = timedOut && loading && !failed && !noticeDismissed;

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
          p: 3,
          pb: 2,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          spacing={2}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h5" component="h1" noWrap>
              {title}
            </Typography>
            {description && (
              <Typography variant="body2" color="text.secondary">
                {description}
              </Typography>
            )}
          </Box>
          {openInNewTab}
        </Stack>
      </Box>

      {showSlowNotice && (
        <Alert
          severity="warning"
          data-testid="embedded-dashboard-slow-notice"
          action={
            <Stack direction="row" spacing={1} alignItems="center">
              {openInNewTab}
              <IconButton
                size="small"
                aria-label={t("close")}
                onClick={() => setNoticeDismissed(true)}
                data-testid="embedded-dashboard-slow-notice-dismiss"
              >
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          }
          sx={{ borderRadius: 0, alignItems: "center" }}
        >
          {t("embedded_dashboard_slow_or_blocked")}
        </Alert>
      )}

      <Box sx={{ position: "relative", flexGrow: 1, minHeight: 0 }}>
        {loading && !failed && (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <CircularProgress data-testid="embedded-dashboard-loading" />
          </Box>
        )}

        {failed ? (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 2,
              p: 3,
              textAlign: "center",
            }}
            data-testid="embedded-dashboard-fallback"
          >
            <Typography variant="body1" color="text.secondary">
              {t("embedded_dashboard_unavailable")}
            </Typography>
            {openInNewTab}
          </Box>
        ) : (
          <Box
            component="iframe"
            src={src}
            title={title}
            data-testid="embedded-dashboard-iframe"
            onLoad={() => setLoading(false)}
            onError={() => {
              setLoading(false);
              setFailed(true);
            }}
            sx={{
              border: 0,
              width: "100%",
              height: "100%",
              display: "block",
            }}
          />
        )}
      </Box>
    </Box>
  );
}

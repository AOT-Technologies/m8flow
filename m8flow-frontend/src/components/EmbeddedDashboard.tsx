import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
  Box,
  Button,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface OwnProps {
  title: string;
  src: string;
  description?: string;
}

/**
 * Renders an external operations dashboard (e.g. Celery Flower, NATS NUI) embedded
 * in an iframe inside the m8flow app shell, with a consistent page header.
 *
 * Some embedded apps may refuse framing via X-Frame-Options / frame-ancestors CSP.
 * The iframe `onError` (and a manual "Open in new tab" action) provide a graceful
 * fallback so the section degrades to a launch link instead of a broken frame.
 */
export default function EmbeddedDashboard({ title, src, description }: OwnProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

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

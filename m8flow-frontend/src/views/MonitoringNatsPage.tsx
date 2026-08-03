import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import UserService from "../services/UserService";
import { useConfig } from "../utils/useConfig";

/**
 * NATS monitoring section.
 *
 * The third-party NUI dashboard this page used to embed has been removed: it could not be
 * extended with the metrics we need (queued/pending counts, consumer lag, stream detail),
 * carried no m8flow authentication or tenant scoping, and could only ever be shown as an
 * opaque cross-origin iframe. The built-in dashboard that replaces it is being added in
 * follow-up work; until then this renders a placeholder so the route, navigation entry and
 * super-admin guard stay wired up.
 */
export default function MonitoringNatsPage() {
  const { t } = useTranslation();
  const { NATS_MONITORING_ENABLED } = useConfig();

  if (!UserService.isSuperAdmin() || !NATS_MONITORING_ENABLED) {
    return <Navigate to="/" replace />;
  }

  return (
    <Box sx={{ p: 3 }} data-testid="nats-monitoring-placeholder">
      <Typography variant="h5" component="h1" gutterBottom>
        {t("nats_monitoring")}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t("nats_monitoring_dashboard_pending")}
      </Typography>
    </Box>
  );
}

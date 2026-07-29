import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import EmbeddedDashboard from "../components/EmbeddedDashboard";
import UserService from "../services/UserService";
import { useConfig } from "../utils/useConfig";

export default function MonitoringCeleryPage() {
  const { t } = useTranslation();
  const { CELERY_FLOWER_URL } = useConfig();

  if (!UserService.isSuperAdmin()) {
    return <Navigate to="/" replace />;
  }

  if (!CELERY_FLOWER_URL) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h5" component="h1" gutterBottom>
          {t("celery_monitoring")}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t("celery_monitoring_not_configured")}
        </Typography>
      </Box>
    );
  }

  // Flower serves its pages under a URL prefix, so the bare base (e.g. "/flower")
  // is not a real route and 404s ("Error, page not found"), while "/flower/workers"
  // is valid. Land the iframe directly on the Workers view so the first load always
  // resolves, regardless of whether the configured URL has a trailing slash.
  const flowerSrc = `${CELERY_FLOWER_URL.replace(/\/+$/, "")}/workers`;

  return (
    <EmbeddedDashboard
      title={t("celery_monitoring")}
      description={t("celery_monitoring_description")}
      src={flowerSrc}
    />
  );
}

import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import EmbeddedDashboard from "../components/EmbeddedDashboard";
import UserService from "../services/UserService";
import { useConfig } from "../utils/useConfig";

export default function MonitoringNatsPage() {
  const { t } = useTranslation();
  const { NATS_UI_URL, NATS_MONITORING_ENABLED } = useConfig();

  if (!UserService.isSuperAdmin() || !NATS_MONITORING_ENABLED) {
    return <Navigate to="/" replace />;
  }

  return (
    <EmbeddedDashboard
      title={t("nats_monitoring")}
      description={t("nats_monitoring_description")}
      src={NATS_UI_URL}
    />
  );
}

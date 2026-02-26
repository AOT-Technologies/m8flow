import React from "react";
import { Box, Tabs, Tab } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useUriListForPermissions } from "@spiffworkflow-frontend/hooks/UriListForPermissions";
import { usePermissionFetcher } from "@spiffworkflow-frontend/hooks/PermissionService";

type HeaderTabsProps = {
  value: number;
  onChange: (event: React.SyntheticEvent, newValue: number) => void;
  taskControlElement: any;
};

export default function HeaderTabs({
  value,
  onChange,
  taskControlElement,
}: HeaderTabsProps) {
  const { t } = useTranslation();
  const { targetUris } = useUriListForPermissions();
  const { ability, permissionsLoaded } = usePermissionFetcher({
    [targetUris.processInstanceListForMePath]: ["POST"],
  });

  if (!permissionsLoaded) return null;

  return (
    <Box
      sx={{
        mb: 2,
        display: "flex",
        justifyContent: "space-between",
        borderWidth: "2px",
        borderBottomStyle: "solid",
        borderColor: "borders.table",
        alignItems: "center",
      }}
    >
      <Tabs
        value={value}
        TabIndicatorProps={{
          style: { height: 3 },
        }}
        onChange={onChange}
        sx={{ flexGrow: 1 }} // Make the Tabs container flexible
      >
        <Tab label={t("tasks_assigned_to_me")} sx={{ textTransform: "none" }} />
        {/* Hide Workflows created by me if user cannot start process instances for me */}
        {ability.can("POST", targetUris.processInstanceListForMePath) && (
          <Tab
            label={t("workflows_created_by_me")}
            sx={{ textTransform: "none" }}
            data-testid="tab-workflows-created-by-me"
          />
        )}
      </Tabs>
      <Box
        sx={{
          display: "flex",
          justifyContent: "right",
          alignItems: "center",
          verticalAlign: "center",
        }}
      >
        {taskControlElement}
      </Box>
    </Box>
  );
}

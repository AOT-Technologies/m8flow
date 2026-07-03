import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Box, Button, CircularProgress } from "@mui/material";
import HttpService from "@spiffworkflow-frontend/services/HttpService";
import TaskShow from "@spiffworkflow-frontend/views/TaskShow/TaskShow";

/**
 * m8flow override for the task page. External-form user tasks render exactly like a
 * normal task (breadcrumb, title, instructions with the secure form link) but must NOT
 * be completable in-app — they wait for the recipient to submit the emailed external
 * form. So we render the upstream TaskShow unchanged and only hide its Submit and
 * signal ("next") buttons for those tasks. Every other task falls through unchanged.
 */
type LoadState = "loading" | "external" | "regular" | "error";

export default function ExternalFormAwareTaskShow() {
  const params = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    let cancelled = false;
    setState("loading");

    HttpService.makeCallToBackend({
      path: `/tasks/${params.process_instance_id}/${params.task_guid}`,
      successCallback: (task: any) => {
        if (cancelled) return;
        // `extensions` is only populated when a task is loaded with form data; the basic
        // task always carries the spec extensions under task_definition_properties_json.
        const externalFormUrl =
          task?.extensions?.properties?.externalFormUrl ??
          task?.task_definition_properties_json?.extensions?.properties
            ?.externalFormUrl;
        setState(externalFormUrl ? "external" : "regular");
      },
      failureCallback: () => {
        // Let the upstream TaskShow handle/report the error consistently.
        if (!cancelled) setState("error");
      },
    });

    return () => {
      cancelled = true;
    };
  }, [params.process_instance_id, params.task_guid]);

  if (state === "loading") {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  // External-form user task: render the normal task page (breadcrumb, title,
  // instructions with the secure form link) but hide ALL in-app action buttons —
  // Submit, signal ("next"), and the upstream "Save and Close" (which writes a draft) —
  // because the recipient completes this task via the emailed external form. We add our
  // own Close button that only navigates away, so there is nothing to *provide* in-app.
  if (state === "external") {
    return (
      <Box
        sx={{
          "& #submit-button": { display: "none" },
          "& #close-button": { display: "none" },
          '& button[name="signal.signal"]': { display: "none" },
        }}
      >
        <TaskShow />
        <Box sx={{ mx: 8, mt: 2 }}>
          {/* Navigate to a fixed destination (Home), not navigate(-1): the task is
              reached via an interstitial redirect, so going "back" bounces straight
              back to this still-open task. Matches upstream "Save and Close". */}
          <Button variant="contained" onClick={() => navigate("/")}>
            Close
          </Button>
        </Box>
      </Box>
    );
  }

  // Regular task (or a load error we defer to upstream): render the upstream task page.
  return <TaskShow />;
}

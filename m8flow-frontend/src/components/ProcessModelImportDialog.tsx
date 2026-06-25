import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  CircularProgress,
  Typography,
  Box,
  Alert,
  InputAdornment,
  Tabs,
  Tab,
} from "@mui/material";
import GitHubIcon from "@mui/icons-material/GitHub";
import TagIcon from "@mui/icons-material/LocalOffer";
import DownloadIcon from "@mui/icons-material/Download";
import HttpService from "@spiffworkflow-frontend/services/HttpService";
import { ProcessModel } from "@spiffworkflow-frontend/interfaces";

interface ProcessModelImportDialogProps {
  open: boolean;
  onClose: () => void;
  processGroupId: string;
  onImportSuccess: (processModelId: string) => void;
}

export function ProcessModelImportDialog({
  open,
  onClose,
  processGroupId,
  onImportSuccess,
}: ProcessModelImportDialogProps) {
  const { t } = useTranslation();
  const [importSource, setImportSource] = useState("");
  const [isValid, setIsValid] = useState<boolean | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [importType, setImportType] = useState<"github" | "marketplace">(
    "github"
  );

  // Validate input based on selected import type
  const validateInput = (value: string): boolean => {
    if (importType === "github") {
      return validateGithubUrl(value);
    } else {
      return validateModelAlias(value);
    }
  };

  const validateGithubUrl = (url: string): boolean => {
    // Basic URL validation
    if (!url || !url.startsWith("https://github.com/")) {
      return false;
    }

    // Validate URL structure: owner/repo/tree|blob/branch/path
    const parts = url.split("/");
    if (parts.length < 7) {
      return false;
    }

    // Check that the URL contains either /tree/ or /blob/
    return url.indexOf("/tree/") !== -1 || url.indexOf("/blob/") !== -1;
  };

  const validateModelAlias = (alias: string): boolean => {
    // Model alias should be a simple string with only alphanumeric characters, hyphens, and underscores
    return /^[a-zA-Z0-9_-]+$/.test(alias);
  };

  const handleSourceChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setImportSource(value);
    if (!value || value.length < 3) {
      setIsValid(null);
    } else {
      setIsValid(validateInput(value));
    }
  };

  const handleTabChange = (
    _event: React.SyntheticEvent,
    newValue: "github" | "marketplace",
  ) => {
    setImportType(newValue);
    setImportSource("");
    setIsValid(null);
  };

  const handleImport = async () => {
    if (!isValid) {
      return;
    }

    // Validate process group ID
    if (!processGroupId || processGroupId.trim() === "") {
      setErrorMessage(t("process_group_id_required_import"));
      return;
    }

    setIsImporting(true);
    setErrorMessage(null);

    try {
      HttpService.makeCallToBackend({
        httpMethod: "POST",
        path: `/process-model-import/${processGroupId}`,
        postBody: {
          repository_url: importSource,
        },
        successCallback: (result: { process_model: ProcessModel }) => {
          if (result && result.process_model && result.process_model.id) {
            const processModelId = result.process_model.id;
            onImportSuccess(processModelId);
            onClose();
          } else {
            console.error(
              "Import response missing expected data structure:",
              result,
            );
            setErrorMessage(t("import_failed_no_id"));
          }
        },
        failureCallback: (error: any) => {
          console.error("Import error:", error);
          setErrorMessage(error?.message || t("import_failed"));
        },
      });
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth data-testid="process-model-import-dialog">
      <DialogTitle>{t("import_process_model")}</DialogTitle>
      <DialogContent>
        <Box sx={{ width: "100%", mb: 2 }}>
          <Tabs
            value={importType}
            onChange={handleTabChange}
            indicatorColor="primary"
            textColor="primary"
            variant="fullWidth"
          >
            <Tab
              value="github"
              label={t("github_repository")}
              icon={<GitHubIcon />}
              iconPosition="start"
              data-testid="import-tab-github"
            />
            <Tab
              value="marketplace"
              label={t("model_marketplace")}
              icon={<TagIcon />}
              iconPosition="start"
              data-testid="import-tab-marketplace"
            />
          </Tabs>
        </Box>
        <Box sx={{ my: 2 }}>
          {importType === "github" ? (
            <>
              <Typography variant="body1" gutterBottom>
                {t("enter_github_url_prompt")}
              </Typography>
              <TextField
                fullWidth
                label={t("github_repository_url")}
                variant="outlined"
                value={importSource}
                onChange={handleSourceChange}
                placeholder={t("github_url_placeholder")}
                margin="normal"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <GitHubIcon />
                    </InputAdornment>
                  ),
                }}
                error={isValid === false}
                helperText={
                  isValid === false
                    ? t("invalid_github_url")
                    : "" //Removed the example GitHub URL referencing Sartography
                }
                disabled={isImporting}
                data-testid="repository-url-input"
              />
            </>
          ) : (
            <>
              <Typography variant="body1" gutterBottom>
                {t("enter_model_alias_prompt")}
              </Typography>
              <TextField
                fullWidth
                label={t("model_alias")}
                variant="outlined"
                value={importSource}
                onChange={handleSourceChange}
                placeholder={t("model_alias_placeholder")}
                margin="normal"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <TagIcon />
                    </InputAdornment>
                  ),
                }}
                error={isValid === false}
                helperText={
                  isValid === false
                    ? t("invalid_model_alias")
                    : t("model_alias_example")
                }
                disabled={isImporting}
                data-testid="model-alias-input"
              />
            </>
          )}

          {/* Error message display */}
          {errorMessage && (
            <Alert severity="error" sx={{ mt: 2 }} data-testid="import-error-alert">
              {errorMessage}
            </Alert>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button data-testid="import-cancel-button" onClick={onClose} disabled={isImporting}>
          {t("cancel")}
        </Button>
        <Button
          onClick={handleImport}
          variant="contained"
          color="primary"
          disabled={!isValid || isImporting}
          startIcon={
            isImporting ? <CircularProgress size={20} /> : <DownloadIcon />
          }
          data-testid="import-button"
        >
          {isImporting ? t("importing") : t("import_model")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

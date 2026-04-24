import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import TemplateService from "../services/TemplateService";
import type { CreateTemplateMetadata, Template, TemplateVisibility } from "../types/template";
import { nameToTemplateKey } from "../utils/templateKey";

export interface ImportTemplateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (template: Template) => void;
}

export default function ImportTemplateModal({
  open,
  onClose,
  onSuccess,
}: ImportTemplateModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [visibility, setVisibility] = useState<TemplateVisibility>("PRIVATE");
  const { t } = useTranslation();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    setFile(f ?? null);
  };

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError(t("name_is_required"));
      return;
    }
    const template_key = nameToTemplateKey(trimmedName);
    if (!template_key) {
      setError(t("name_must_contain_letter_or_number"));
      return;
    }
    if (!file) {
      setError(t("please_select_zip_file"));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const metadata: CreateTemplateMetadata = {
        template_key,
        name: trimmedName,
        visibility,
      };
      const template = await TemplateService.importTemplate(file, metadata);
      onClose();
      onSuccess?.(template);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("import_failed"));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setName("");
    setFile(null);
    setVisibility("PRIVATE");
    setError(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth data-testid="import-template-dialog">
      <DialogTitle>{t("import_template_from_zip")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1 }} data-testid="import-template-error-alert">{error}</Alert>
          )}
          <TextField
            label={t("name")}
            required
            fullWidth
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            placeholder={t("eg_my_workflow")}
            data-testid="import-template-name-input"
          />
          <FormControl fullWidth size="medium">
            <InputLabel id="import-visibility-label">{t("visibility")}</InputLabel>
            <Select
              labelId="import-visibility-label"
              label={t("visibility")}
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as TemplateVisibility)}
              disabled={loading}
              data-testid="import-template-visibility-select"
            >
              <MenuItem value="PRIVATE">{t("private")}</MenuItem>
              <MenuItem value="TENANT">{t("tenant")}</MenuItem>
              <MenuItem value="PUBLIC">{t("public")}</MenuItem>
            </Select>
          </FormControl>
          <Button variant="outlined" component="label" disabled={loading} data-testid="import-template-choose-file-button">
            {file ? file.name : t("choose_zip_file")}
            <input
              type="file"
              hidden
              accept=".zip"
              onChange={handleFileChange}
            />
          </Button>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button data-testid="import-template-cancel-button" onClick={handleClose} disabled={loading}>
          {t("cancel")}
        </Button>
        <Button data-testid="import-template-submit-button" variant="contained" onClick={handleSubmit} disabled={loading}>
          {loading ? t("importing") : t("import")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

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
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import TemplateService from "../services/TemplateService";
import { nameToTemplateKey } from "../utils/templateKey";
import { VISIBILITY_OPTIONS } from "../utils/templateHelpers";
import type { CreateTemplateMetadata, Template, TemplateVisibility } from "../types/template";

const SUPPORTED_EXT = [".bpmn", ".json", ".dmn", ".md"];

export interface SaveAsTemplateFile {
  name: string;
  content: Blob;
}

export interface SaveAsTemplateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (template?: Template) => void;
  /** Return all files to save with the template (at least one must be .bpmn). */
  getFiles: () => Promise<SaveAsTemplateFile[]>;
}

export default function SaveAsTemplateModal({
  open,
  onClose,
  onSuccess,
  getFiles,
}: SaveAsTemplateModalProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState("");
  const [visibility, setVisibility] = useState<TemplateVisibility>("PRIVATE");

  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
      setCategory("");
      setTags("");
      setVisibility("PRIVATE");
      setError(null);
    }
  }, [open]);

  const handleSubmit = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError(t("name_required"));
      return;
    }
    const template_key = nameToTemplateKey(trimmedName);
    if (!template_key) {
      setError(t("name_must_contain_letter_or_number"));
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const files = await getFiles();
      if (!files?.length) {
        setError(t("no_files_to_save"));
        setLoading(false);
        return;
      }
      const hasBpmn = files.some((f) =>
        f.name.toLowerCase().endsWith(".bpmn")
      );
      if (!hasBpmn) {
        setError(t("at_least_one_bpmn_required"));
        setLoading(false);
        return;
      }
      const metadata: CreateTemplateMetadata = {
        template_key,
        name: trimmedName,
        visibility,
      };
      if (description.trim()) metadata.description = description.trim();
      if (category.trim()) metadata.category = category.trim();
      if (tags.trim()) {
        metadata.tags = tags.split(",").map((s) => s.trim()).filter(Boolean);
      }
      const filesForApi = files.map((f) => ({ name: f.name, content: f.content }));
      const template = await TemplateService.createTemplateWithFiles(
        metadata,
        filesForApi
      );
      onClose();
      onSuccess?.(template);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : t("failed_to_create_template_retry");
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      data-testid="save-as-template-dialog"
    >
      <DialogTitle sx={{ fontSize: "1.25rem", fontWeight: 600 }}>
        {t("save_as_template")}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ pt: 1 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1 }} data-testid="save-as-template-error-alert">{error}</Alert>
          )}
          <TextField
            label={t("name")}
            fullWidth
            required
            placeholder={t("eg_approval_workflow")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            data-testid="save-as-template-name-input"
          />
          <TextField
            label={t("description")}
            fullWidth
            multiline
            minRows={2}
            placeholder={t("optional_description")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={loading}
            data-testid="save-as-template-description-input"
          />
          <TextField
            label={t("category")}
            fullWidth
            placeholder={t("optional_category")}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={loading}
            data-testid="save-as-template-category-input"
          />
          <TextField
            label={t("tags")}
            fullWidth
            placeholder={t("comma_separated_tags")}
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            disabled={loading}
            data-testid="save-as-template-tags-input"
          />
          <FormControl fullWidth disabled={loading}>
            <InputLabel>{t("visibility")}</InputLabel>
            <Select
              value={visibility}
              label={t("visibility")}
              data-testid="save-as-template-visibility-select"
              onChange={(e) => setVisibility(e.target.value as TemplateVisibility)}
            >
              {VISIBILITY_OPTIONS.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>
                  {t(opt.labelKey)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button data-testid="save-as-template-cancel-button" onClick={onClose} disabled={loading} variant="outlined">
          {t("cancel")}
        </Button>
        <Button
          data-testid="save-as-template-submit-button"
          onClick={handleSubmit}
          variant="contained"
          color="primary"
          disabled={loading}
        >
          {loading ? t("creating") : t("create_template")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

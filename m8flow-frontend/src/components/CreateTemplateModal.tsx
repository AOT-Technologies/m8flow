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
import type { CreateTemplateMetadata, Template, TemplateVisibility } from "../types/template";
import { nameToTemplateKey } from "../utils/templateKey";
import { VISIBILITY_OPTIONS } from "../utils/templateHelpers";

export interface CreateTemplateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (template: Template) => void;
}

export default function CreateTemplateModal({
  open,
  onClose,
  onSuccess,
}: CreateTemplateModalProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState("");
  const [visibility, setVisibility] = useState<TemplateVisibility>("PRIVATE");
  const [files, setFiles] = useState<File[]>([]);

  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
      setCategory("");
      setTags("");
      setVisibility("PRIVATE");
      setFiles([]);
      setError(null);
    }
  }, [open]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files;
    if (selected) {
      setFiles(Array.from(selected));
    }
  };

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
    const hasBpmn = files.some(
      (f) => f.name.toLowerCase().endsWith(".bpmn")
    );
    if (!hasBpmn) {
      setError(t("at_least_one_bpmn_required"));
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
      if (description.trim()) metadata.description = description.trim();
      if (category.trim()) metadata.category = category.trim();
      if (tags.trim()) {
        metadata.tags = tags.split(",").map((s) => s.trim()).filter(Boolean);
      }
      const filesWithContent = files.map((f) => ({
        name: f.name,
        content: f,
      }));
      const template = await TemplateService.createTemplateWithFiles(
        metadata,
        filesWithContent
      );
      onClose();
      onSuccess?.(template);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : t("failed_to_create_template")
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="create-template-dialog">
      <DialogTitle>{t("create_template_title")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1 }} data-testid="create-template-error-alert">{error}</Alert>
          )}
          <TextField
            label={t("name")}
            required
            fullWidth
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            placeholder={t("eg_approval_workflow")}
            data-testid="create-template-name-input"
          />
          <TextField
            label={t("description")}
            fullWidth
            multiline
            minRows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={loading}
            data-testid="create-template-description-input"
          />
          <TextField
            label={t("category")}
            fullWidth
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={loading}
            data-testid="create-template-category-input"
          />
          <TextField
            label={t("tags")}
            fullWidth
            placeholder={t("comma_separated")}
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            disabled={loading}
            data-testid="create-template-tags-input"
          />
          <FormControl fullWidth disabled={loading}>
            <InputLabel>{t("visibility")}</InputLabel>
            <Select
              value={visibility}
              label={t("visibility")}
              data-testid="create-template-visibility-select"
              onChange={(e) =>
                setVisibility(e.target.value as TemplateVisibility)
              }
            >
              {VISIBILITY_OPTIONS.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>
                  {t(opt.labelKey)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button variant="outlined" component="label" disabled={loading} data-testid="create-template-choose-files-button">
            {files.length > 0
              ? t("files_selected_include_bpmn", { count: files.length })
              : t("choose_files_bpmn_required")}
            <input
              type="file"
              hidden
              multiple
              accept=".bpmn,.json,.dmn,.md"
              onChange={handleFileChange}
            />
          </Button>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button data-testid="create-template-cancel-button" onClick={onClose} disabled={loading}>
          {t("cancel")}
        </Button>
        <Button data-testid="create-template-submit-button" variant="contained" onClick={handleSubmit} disabled={loading}>
          {loading ? t("creating") : t("create")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

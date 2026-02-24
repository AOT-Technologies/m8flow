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
import TemplateService from "../services/TemplateService";
import { nameToTemplateKey } from "../utils/templateKey";
import type { CreateTemplateMetadata, Template, TemplateVisibility } from "../types/template";

const VISIBILITY_OPTIONS: { value: TemplateVisibility; label: string }[] = [
  { value: "PRIVATE", label: "Private (only you)" },
  { value: "TENANT", label: "Tenant-wide (all users in your tenant)" },
];

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
      setError("Name is required.");
      return;
    }
    const template_key = nameToTemplateKey(trimmedName);
    if (!template_key) {
      setError("Name must contain at least one letter or number.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const files = await getFiles();
      if (!files?.length) {
        setError("No files to save. Please try again.");
        setLoading(false);
        return;
      }
      const hasBpmn = files.some((f) =>
        f.name.toLowerCase().endsWith(".bpmn")
      );
      if (!hasBpmn) {
        setError("At least one BPMN file is required.");
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
        err instanceof Error ? err.message : "Failed to create template. Please try again.";
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
    >
      <DialogTitle sx={{ fontSize: "1.25rem", fontWeight: 600 }}>
        Save as Template
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ pt: 1 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>
          )}
          <TextField
            label="Name"
            fullWidth
            required
            placeholder="e.g. Approval Workflow"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
          />
          <TextField
            label="Description"
            fullWidth
            multiline
            minRows={2}
            placeholder="Optional description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={loading}
          />
          <TextField
            label="Category"
            fullWidth
            placeholder="Optional category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={loading}
          />
          <TextField
            label="Tags"
            fullWidth
            placeholder="Comma-separated tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            disabled={loading}
          />
          <FormControl fullWidth disabled={loading}>
            <InputLabel>Visibility</InputLabel>
            <Select
              value={visibility}
              label="Visibility"
              onChange={(e) => setVisibility(e.target.value as TemplateVisibility)}
            >
              {VISIBILITY_OPTIONS.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>
                  {opt.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button onClick={onClose} disabled={loading} variant="outlined">
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          color="primary"
          disabled={loading}
        >
          {loading ? "Creating..." : "Create Template"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

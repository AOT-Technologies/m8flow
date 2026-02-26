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
import type { CreateTemplateMetadata, Template, TemplateVisibility } from "../types/template";
import { nameToTemplateKey } from "../utils/templateKey";

const VISIBILITY_OPTIONS: { value: TemplateVisibility; label: string }[] = [
  { value: "PRIVATE", label: "Private (only you)" },
  { value: "TENANT", label: "Tenant-wide (all users in your tenant)" },
];

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
      setError("Name is required.");
      return;
    }
    const template_key = nameToTemplateKey(trimmedName);
    if (!template_key) {
      setError("Name must contain at least one letter or number.");
      return;
    }
    const hasBpmn = files.some(
      (f) => f.name.toLowerCase().endsWith(".bpmn")
    );
    if (!hasBpmn) {
      setError("At least one BPMN file is required.");
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
        err instanceof Error ? err.message : "Failed to create template."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Create template</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>
          )}
          <TextField
            label="Name"
            required
            fullWidth
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
            placeholder="e.g. Approval Workflow"
          />
          <TextField
            label="Description"
            fullWidth
            multiline
            minRows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={loading}
          />
          <TextField
            label="Category"
            fullWidth
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={loading}
          />
          <TextField
            label="Tags"
            fullWidth
            placeholder="Comma-separated"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            disabled={loading}
          />
          <FormControl fullWidth disabled={loading}>
            <InputLabel>Visibility</InputLabel>
            <Select
              value={visibility}
              label="Visibility"
              onChange={(e) =>
                setVisibility(e.target.value as TemplateVisibility)
              }
            >
              {VISIBILITY_OPTIONS.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>
                  {opt.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button variant="outlined" component="label" disabled={loading}>
            {files.length > 0
              ? `${files.length} file(s) selected (include .bpmn)`
              : "Choose files (BPMN required)"}
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
        <Button onClick={onClose} disabled={loading}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleSubmit} disabled={loading}>
          {loading ? "Creating..." : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

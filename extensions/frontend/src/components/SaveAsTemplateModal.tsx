import {
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

const VISIBILITY_OPTIONS: { value: TemplateVisibility; label: string }[] = [
  { value: "PRIVATE", label: "Private (only you)" },
  { value: "TENANT", label: "Tenant-wide (all users in your tenant)" },
];

export interface SaveAsTemplateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (template?: Template) => void;
  getBpmnXml: () => Promise<string>;
}

export default function SaveAsTemplateModal({
  open,
  onClose,
  onSuccess,
  getBpmnXml,
}: SaveAsTemplateModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [templateKey, setTemplateKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState("");
  const [visibility, setVisibility] = useState<TemplateVisibility>("PRIVATE");

  useEffect(() => {
    if (!open) {
      setTemplateKey("");
      setName("");
      setDescription("");
      setCategory("");
      setTags("");
      setVisibility("PRIVATE");
      setError(null);
    }
  }, [open]);

  const handleSubmit = async () => {
    const trimmedKey = templateKey.trim();
    const trimmedName = name.trim();
    if (!trimmedKey) {
      setError("Template key is required.");
      return;
    }
    if (!trimmedName) {
      setError("Name is required.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const bpmnXml = await getBpmnXml();
      if (!bpmnXml || !bpmnXml.trim()) {
        setError("Could not get diagram content. Please try again.");
        setLoading(false);
        return;
      }
      const metadata: CreateTemplateMetadata = {
        template_key: trimmedKey,
        name: trimmedName,
        visibility,
      };
      if (description.trim()) metadata.description = description.trim();
      if (category.trim()) metadata.category = category.trim();
      if (tags.trim()) {
        metadata.tags = tags.split(",").map((s) => s.trim()).filter(Boolean);
      }
      const template = await TemplateService.createTemplate(bpmnXml, metadata);
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
            <TextField
              fullWidth
              size="small"
              value={error}
              error
              multiline
              minRows={1}
              InputProps={{ readOnly: true }}
              sx={{ "& .MuiInputBase-input": { color: "error.main" } }}
            />
          )}
          <TextField
            label="Template key"
            fullWidth
            required
            placeholder="e.g. approval-workflow"
            value={templateKey}
            onChange={(e) => setTemplateKey(e.target.value)}
            disabled={loading}
            helperText="Unique identifier (letters, numbers, hyphens)"
          />
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

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import { useState } from "react";
import TemplateService from "../services/TemplateService";
import type { CreateTemplateMetadata, Template } from "../types/template";
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    setFile(f ?? null);
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
    if (!file) {
      setError("Please select a zip file.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const metadata: CreateTemplateMetadata = {
        template_key,
        name: trimmedName,
      };
      const template = await TemplateService.importTemplate(file, metadata);
      onClose();
      onSuccess?.(template);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Import failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setName("");
    setFile(null);
    setError(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Import template from zip</DialogTitle>
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
            placeholder="e.g. My Workflow"
          />
          <Button variant="outlined" component="label" disabled={loading}>
            {file ? file.name : "Choose zip file"}
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
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleSubmit} disabled={loading}>
          {loading ? "Importing..." : "Import"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

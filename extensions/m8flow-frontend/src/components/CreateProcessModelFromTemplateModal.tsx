import {
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ProcessGroup, ProcessGroupLite } from "@spiffworkflow-frontend/interfaces";
import TemplateService from "../services/TemplateService";
import useProcessGroups from "../hooks/useProcessGroups";
import { nameToTemplateKey } from "../utils/templateKey";
import type { Template } from "../types/template";

/**
 * Flatten process groups into a list of { id, displayName } for the autocomplete.
 */
function flattenProcessGroups(
  groups: (ProcessGroup | ProcessGroupLite)[] | null,
  parentPath = ""
): { id: string; displayName: string }[] {
  if (!groups) return [];
  const result: { id: string; displayName: string }[] = [];
  for (const group of groups) {
    const id = group.id;
    const displayName = group.display_name || id;
    result.push({ id, displayName: parentPath ? `${parentPath} / ${displayName}` : displayName });
    // Recursively add child groups if they exist
    if ("process_groups" in group && Array.isArray(group.process_groups)) {
      result.push(
        ...flattenProcessGroups(
          group.process_groups as ProcessGroup[],
          parentPath ? `${parentPath} / ${displayName}` : displayName
        )
      );
    }
  }
  return result;
}

export interface CreateProcessModelFromTemplateModalProps {
  open: boolean;
  onClose: () => void;
  template: Template | null;
  onSuccess?: (processModelId: string) => void;
}

export default function CreateProcessModelFromTemplateModal({
  open,
  onClose,
  template,
  onSuccess,
}: Readonly<CreateProcessModelFromTemplateModalProps>) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form fields
  const [selectedGroup, setSelectedGroup] = useState<{ id: string; displayName: string } | null>(null);
  const [processModelId, setProcessModelId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [idManuallyEdited, setIdManuallyEdited] = useState(false);

  // Fetch process groups
  const { processGroups, loading: groupsLoading } = useProcessGroups({ processInfo: {} });
  const flattenedGroups = useMemo(() => flattenProcessGroups(processGroups), [processGroups]);

  // Reset form when modal opens/closes
  useEffect(() => {
    if (!open) {
      setSelectedGroup(null);
      setProcessModelId("");
      setDisplayName("");
      setDescription("");
      setIdManuallyEdited(false);
      setError(null);
    } else if (template) {
      // Pre-fill display name from template name
      setDisplayName(template.name);
      setProcessModelId(nameToTemplateKey(template.name));
      setDescription(template.description || "");
    }
  }, [open, template?.id]);

  // Auto-generate process model ID from display name (unless manually edited)
  const handleDisplayNameChange = (value: string) => {
    setDisplayName(value);
    if (!idManuallyEdited) {
      setProcessModelId(nameToTemplateKey(value));
    }
  };

  const handleProcessModelIdChange = (value: string) => {
    setProcessModelId(value);
    setIdManuallyEdited(true);
  };

  const handleSubmit = async () => {
    // Validation
    if (!selectedGroup) {
      setError("Please select a process group.");
      return;
    }
    const trimmedId = processModelId.trim();
    if (!trimmedId) {
      setError("Process model ID is required.");
      return;
    }
    if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$/.test(trimmedId)) {
      setError("Process model ID must contain only lowercase letters, numbers, and hyphens, and cannot start or end with a hyphen.");
      return;
    }
    const trimmedName = displayName.trim();
    if (!trimmedName) {
      setError("Display name is required.");
      return;
    }
    if (!template) {
      setError("No template selected.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await TemplateService.createProcessModelFromTemplate(template.id, {
        process_group_id: selectedGroup.id,
        process_model_id: trimmedId,
        display_name: trimmedName,
        description: description.trim() || undefined,
      });

      const fullProcessModelId = result.template_info?.process_model_identifier || `${selectedGroup.id}/${trimmedId}`;
      
      if (onSuccess) {
        onSuccess(fullProcessModelId);
      } else {
        // Navigate to the new process model
        const encodedId = fullProcessModelId.replaceAll("/", ":");
        navigate(`/process-models/${encodedId}`);
      }
      onClose();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to create process model. Please try again.";
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
        Create Process Model from Template
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ pt: 1 }}>
          {template && (
            <Alert severity="info" sx={{ mb: 1 }}>
              Creating from template: <strong>{template.name}</strong> ({template.version})
            </Alert>
          )}
          {error && (
            <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>
          )}
          
          <Box>
            <Autocomplete
              options={flattenedGroups}
              getOptionLabel={(option) => option.displayName}
              value={selectedGroup}
              onChange={(_, newValue) => setSelectedGroup(newValue)}
              loading={groupsLoading}
              disabled={loading}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Process Group"
                  required
                  placeholder="Select a process group"
                  InputProps={{
                    ...params.InputProps,
                    endAdornment: (
                      <>
                        {groupsLoading ? <CircularProgress color="inherit" size={20} /> : null}
                        {params.InputProps.endAdornment}
                      </>
                    ),
                  }}
                />
              )}
            />
            {!groupsLoading && flattenedGroups.length === 0 && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                No process groups found.{" "}
                <Link href="/process-groups/new" target="_blank" rel="noopener">
                  Create a process group
                </Link>{" "}
                first, then return here.
              </Alert>
            )}
          </Box>

          <TextField
            label="Display Name"
            fullWidth
            required
            placeholder="e.g. My Approval Workflow"
            value={displayName}
            onChange={(e) => handleDisplayNameChange(e.target.value)}
            disabled={loading}
            helperText="Human-readable name for the process model"
          />

          <TextField
            label="Process Model ID"
            fullWidth
            required
            placeholder="e.g. my-approval-workflow"
            value={processModelId}
            onChange={(e) => handleProcessModelIdChange(e.target.value)}
            disabled={loading}
            helperText="Unique identifier (lowercase letters, numbers, and hyphens only)"
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

          {selectedGroup && processModelId && (
            <Typography variant="body2" color="text.secondary">
              Full path: <code>{selectedGroup.id}/{processModelId}</code>
            </Typography>
          )}
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
          disabled={loading || groupsLoading}
        >
          {loading ? "Creating..." : "Create Process Model"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

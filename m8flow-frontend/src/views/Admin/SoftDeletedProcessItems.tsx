import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Tabs,
  Tab,
  Alert,
  CircularProgress,
  Stack,
  Chip,
} from '@mui/material';
import { RestoreFromTrash, DeleteForever } from '@mui/icons-material';
import HttpService from '../../services/HttpService';
import useAPIError from '../../hooks/UseApiError';

interface DeletionRecord {
  id: number;
  original_identifier: string;
  deleted_identifier: string;
  display_name: string;
  parent_group_id: string | null;
  status: string;
  deleted_at_in_seconds: number;
  deleted_by: string;
  m8f_tenant_id: string;
}

interface PaginatedResponse {
  results: DeletionRecord[];
  pagination: {
    count: number;
    total: number;
    pages: number;
    page: number;
  };
}

export default function SoftDeletedProcessItems() {
  const { t } = useTranslation();
  const { addError, removeError } = useAPIError();
  const [tabIndex, setTabIndex] = useState(0);
  const [models, setModels] = useState<DeletionRecord[]>([]);
  const [groups, setGroups] = useState<DeletionRecord[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [purgeDialogOpen, setPurgeDialogOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<DeletionRecord | null>(null);
  const [newIdentifier, setNewIdentifier] = useState('');
  const [newDisplayName, setNewDisplayName] = useState('');
  const [conflictError, setConflictError] = useState<string | null>(null);
  const [itemType, setItemType] = useState<'model' | 'group'>('model');

  const fetchModels = () => {
    setLoadingModels(true);
    HttpService.makeCallToBackend({
      path: '/m8flow/admin/process-models/deleted',
      successCallback: (result: PaginatedResponse) => {
        setModels(result.results);
        setLoadingModels(false);
      },
      failureCallback: (err: any) => {
        addError(err);
        setLoadingModels(false);
      },
    });
  };

  const fetchGroups = () => {
    setLoadingGroups(true);
    HttpService.makeCallToBackend({
      path: '/m8flow/admin/process-groups/deleted',
      successCallback: (result: PaginatedResponse) => {
        setGroups(result.results);
        setLoadingGroups(false);
      },
      failureCallback: (err: any) => {
        addError(err);
        setLoadingGroups(false);
      },
    });
  };

  useEffect(() => {
    fetchModels();
    fetchGroups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRestore = (item: DeletionRecord, type: 'model' | 'group') => {
    setSelectedItem(item);
    setItemType(type);
    setNewIdentifier('');
    setNewDisplayName('');
    setConflictError(null);
    doRestore(item, type, null, null);
  };

  const doRestore = (
    item: DeletionRecord,
    type: 'model' | 'group',
    identifier: string | null,
    displayName: string | null,
  ) => {
    removeError();
    const basePath =
      type === 'model'
        ? '/m8flow/admin/process-models/deleted'
        : '/m8flow/admin/process-groups/deleted';
    const body: Record<string, string> = {};
    if (identifier) body.new_identifier = identifier;
    if (displayName) body.new_display_name = displayName;

    HttpService.makeCallToBackend({
      path: `${basePath}/${item.id}/restore`,
      httpMethod: 'POST',
      postBody: body,
      successCallback: () => {
        setRestoreDialogOpen(false);
        setSelectedItem(null);
        fetchModels();
        fetchGroups();
      },
      failureCallback: (err: any) => {
        if (err?.error_code === 'original_name_in_use') {
          setConflictError(
            err.message ||
              'The original name is already in use. Please provide a new identifier.',
          );
          setRestoreDialogOpen(true);
        } else {
          addError(err);
        }
      },
    });
  };

  const handleRestoreWithNewName = () => {
    if (!selectedItem) return;
    doRestore(
      selectedItem,
      itemType,
      newIdentifier || null,
      newDisplayName || null,
    );
  };

  const handlePurgeClick = (item: DeletionRecord) => {
    setSelectedItem(item);
    setPurgeDialogOpen(true);
  };

  const confirmPurge = () => {
    if (!selectedItem) return;
    removeError();
    HttpService.makeCallToBackend({
      path: `/m8flow/admin/process-models/deleted/${selectedItem.id}/purge`,
      httpMethod: 'POST',
      successCallback: () => {
        setPurgeDialogOpen(false);
        setSelectedItem(null);
        fetchModels();
      },
      failureCallback: (err: any) => {
        setPurgeDialogOpen(false);
        setSelectedItem(null);
        addError(err);
      },
    });
  };

  const formatTimestamp = (seconds: number) => {
    return new Date(seconds * 1000).toLocaleString();
  };

  const renderTable = (
    items: DeletionRecord[],
    type: 'model' | 'group',
  ) => {
    const isLoading = type === 'model' ? loadingModels : loadingGroups;
    if (isLoading) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      );
    }
    if (items.length === 0) {
      return (
        <Alert severity="info" sx={{ mt: 2 }}>
          {type === 'model'
            ? t('no_deleted_process_models', {
                defaultValue: 'No soft-deleted process models found.',
              })
            : t('no_deleted_process_groups', {
                defaultValue: 'No soft-deleted process groups found.',
              })}
        </Alert>
      );
    }
    return (
      <TableContainer component={Paper} sx={{ mt: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('name', { defaultValue: 'Name' })}</TableCell>
              <TableCell>
                {t('original_id', { defaultValue: 'Original ID' })}
              </TableCell>
              <TableCell>
                {t('deleted_at', { defaultValue: 'Deleted At' })}
              </TableCell>
              <TableCell>
                {t('deleted_by', { defaultValue: 'Deleted By' })}
              </TableCell>
              <TableCell>{t('actions', { defaultValue: 'Actions' })}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2">{item.display_name}</Typography>
                    <Chip label={item.status} size="small" color="warning" />
                  </Stack>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {item.original_identifier}
                  </Typography>
                </TableCell>
                <TableCell>
                  {formatTimestamp(item.deleted_at_in_seconds)}
                </TableCell>
                <TableCell>{item.deleted_by}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={1}>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<RestoreFromTrash />}
                      onClick={() => handleRestore(item, type)}
                    >
                      {t('restore', { defaultValue: 'Restore' })}
                    </Button>
                    {type === 'model' && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteForever />}
                        onClick={() => handlePurgeClick(item)}
                      >
                        {t('purge', { defaultValue: 'Purge' })}
                      </Button>
                    )}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h4" component="h1" sx={{ mb: 3 }}>
        {t('deleted_processes', {
          defaultValue: 'Deleted Process Models & Groups',
        })}
      </Typography>

      <Tabs value={tabIndex} onChange={(_, v) => setTabIndex(v)}>
        <Tab
          label={t('process_models', { defaultValue: 'Process Models' })}
        />
        <Tab
          label={t('process_groups', { defaultValue: 'Process Groups' })}
        />
      </Tabs>

      {tabIndex === 0 && renderTable(models, 'model')}
      {tabIndex === 1 && renderTable(groups, 'group')}

      <Dialog
        open={restoreDialogOpen}
        onClose={() => setRestoreDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {t('restore_with_new_name', {
            defaultValue: 'Restore with New Name',
          })}
        </DialogTitle>
        <DialogContent>
          {conflictError && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {conflictError}
            </Alert>
          )}
          <TextField
            autoFocus
            margin="dense"
            label={t('new_identifier', { defaultValue: 'New Identifier' })}
            fullWidth
            variant="outlined"
            value={newIdentifier}
            onChange={(e) => setNewIdentifier(e.target.value)}
            helperText={t('new_identifier_help', {
              defaultValue:
                'Enter a new unique process identifier (e.g., my-group/my-new-model)',
            })}
          />
          {itemType === 'model' && (
            <TextField
              margin="dense"
              label={t('new_display_name', {
                defaultValue: 'New Display Name (optional)',
              })}
              fullWidth
              variant="outlined"
              value={newDisplayName}
              onChange={(e) => setNewDisplayName(e.target.value)}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRestoreDialogOpen(false)}>
            {t('cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            onClick={handleRestoreWithNewName}
            variant="contained"
            disabled={!newIdentifier}
          >
            {t('restore', { defaultValue: 'Restore' })}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={purgeDialogOpen}
        onClose={() => setPurgeDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {t('confirm_purge', {
            defaultValue: 'Permanently Delete',
          })}
        </DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 2 }}>
            {t('purge_warning', {
              defaultValue:
                'This action is irreversible. The process model and all its files will be permanently deleted.',
            })}
          </Alert>
          {selectedItem && (
            <Typography variant="body1">
              {t('purge_confirm_message', {
                name: selectedItem.display_name,
                defaultValue: `Are you sure you want to permanently delete "${selectedItem.display_name}"?`,
              })}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPurgeDialogOpen(false)}>
            {t('cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            onClick={confirmPurge}
            variant="contained"
            color="error"
          >
            {t('purge', { defaultValue: 'Purge' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

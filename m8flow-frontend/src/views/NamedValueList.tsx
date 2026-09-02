import { useEffect, useState } from 'react';
import AddIcon from '@mui/icons-material/Add';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import HttpService from '../services/HttpService';

type NamedValue = {
  id: string;
  name: string;
  description?: string | null;
  isSensitive: boolean;
  isConfigured: boolean;
  value: unknown;
};

const errorMessage = (error: any) =>
  error?.message || error?.detail || 'Could not load named values.';

export default function NamedValueList() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<NamedValue[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isSensitive, setIsSensitive] = useState(false);

  const load = () => {
    HttpService.makeCallToBackend({
      path: '/m8flow/named-values',
      successCallback: (payload: { values?: NamedValue[] }) => {
        setRows(payload.values ?? []);
        setLoaded(true);
        setError('');
      },
      failureCallback: (reason: unknown) => {
        setLoaded(true);
        setError(errorMessage(reason));
      },
    });
  };

  useEffect(load, []);

  const saveEdit = () => {
    if (!editingId) return;
    setError('');
    HttpService.makeCallToBackend({
      path: `/m8flow/named-values/${editingId}`,
      httpMethod: 'PUT',
      postBody: { name, description: description || null, value, is_sensitive: isSensitive },
      successCallback: () => {
        setName('');
        setDescription('');
        setValue('');
        setEditingId(null);
        setIsSensitive(false);
        load();
      },
      failureCallback: (reason: unknown) => setError(errorMessage(reason)),
    });
  };

  const closeEdit = () => {
    setEditingId(null);
    setName('');
    setDescription('');
    setValue('');
    setIsSensitive(false);
  };

  const edit = (row: NamedValue) => {
    setEditingId(row.id);
    setName(row.name);
    setDescription(row.description || '');
    setIsSensitive(row.isSensitive);
    // Do not retrieve or prefill a sensitive value from the provider.
    setValue(row.isSensitive ? '' : (typeof row.value === 'string' ? row.value : JSON.stringify(row.value)));
  };

  const remove = (id: string) => {
    HttpService.makeCallToBackend({
      path: `/m8flow/named-values/${id}`,
      httpMethod: 'DELETE',
      successCallback: load,
      failureCallback: (reason: unknown) => setError(errorMessage(reason)),
    });
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h1">Configuration Variables</Typography>
          <Typography variant="body2">
            Reusable values for the selected tenant. Sensitive values are stored by
            the configured secret provider and are never shown here.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => navigate('/configuration/secrets/new')}
        >
          Add variable
        </Button>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {loaded && rows.length === 0 ? (
        <Typography>No configuration variables are available.</Typography>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Description</TableCell><TableCell>Value</TableCell><TableCell>Action</TableCell></TableRow></TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.name}</TableCell>
                  <TableCell>{row.description || '-'}</TableCell>
                  <TableCell>{row.isSensitive ? (row.isConfigured ? 'Configured' : 'Not configured') : (typeof row.value === 'string' ? row.value : JSON.stringify(row.value))}</TableCell>
                  <TableCell><Button onClick={() => edit(row)}>Edit</Button><Button color="error" onClick={() => remove(row.id)}>Delete</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <Dialog open={editingId !== null} onClose={closeEdit} fullWidth maxWidth="sm">
        <DialogTitle>Edit configuration variable</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField required label="Name" value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
            <TextField required={!isSensitive} type={isSensitive ? 'password' : 'text'} label="Value" value={value} onChange={(e) => setValue(e.target.value)} helperText={isSensitive ? 'Leave blank to retain the configured value.' : ''} />
            <FormControlLabel control={<Checkbox checked={isSensitive} onChange={(e) => setIsSensitive(e.target.checked)} />} label="Sensitive value" />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEdit}>Cancel</Button>
          <Button variant="contained" onClick={saveEdit}>Save changes</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

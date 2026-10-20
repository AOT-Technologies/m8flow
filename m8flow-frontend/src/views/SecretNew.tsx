import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Checkbox, FormControlLabel, TextField, Button, Stack, Box, Typography } from '@mui/material';
import HttpService from '../services/HttpService';
import { validateNamedValueName } from './namedValueValidation';

export default function SecretNew() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');
  const [description, setDescription] = useState('');
  const [isSensitive, setIsSensitive] = useState(false);
  const [keyError, setKeyError] = useState(false);
  const [valueError, setValueError] = useState(false);
  const [keyErrorMessage, setKeyErrorMessage] = useState('');
  const [valueErrorMessage, setValueErrorMessage] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const keyValidationMessage = validateNamedValueName(key);
    const invalidKey = Boolean(keyValidationMessage);
    const invalidValue = !value.trim();
    setKeyError(invalidKey);
    setValueError(invalidValue);
    setKeyErrorMessage(invalidKey ? keyValidationMessage : '');
    setValueErrorMessage(invalidValue ? 'Value is required.' : '');
    if (invalidKey || invalidValue) {
      return;
    }
    HttpService.makeCallToBackend({
      path: '/m8flow/named-values',
      httpMethod: 'POST',
      postBody: {
        name: key,
        value,
        description: description || null,
        is_sensitive: isSensitive,
      },
      failureCallback: (reason: { error_code?: string; message?: string }) => {
        const message = reason?.message || 'Could not save configuration variable.';
        if (reason?.error_code === 'duplicate_name') {
          setKeyError(true);
          setKeyErrorMessage(message);
        } else if (reason?.error_code === 'invalid_value' || reason?.error_code === 'value_required') {
          setValueError(true);
          setValueErrorMessage(message);
        } else {
          setKeyError(true);
          setKeyErrorMessage(message);
        }
      },
      successCallback: () => navigate('/configuration/named-values'),
    });
  };

  return (
    <Box component="main" sx={{ padding: '1rem 0' }}>
      <Typography variant="h4" component="h1" gutterBottom>Add variable</Typography>
      <form onSubmit={submit}>
        <Stack spacing={2}>
          <TextField
            id="secret-key"
            label={`${isSensitive ? t('secret_key') : 'Name'} *`}
            value={key}
            error={keyError}
            helperText={keyError ? keyErrorMessage : ''}
            onChange={(e) => {
              setKey(e.target.value);
              setKeyError(false);
              setKeyErrorMessage('');
            }}
            inputProps={{ maxLength: 255 }}
            fullWidth
          />
          <TextField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} fullWidth />
          <TextField
            id="secret-value"
            type={isSensitive ? 'password' : 'text'}
            label={`${t('value')} *`}
            value={value}
            error={valueError}
            helperText={valueError ? valueErrorMessage : ''}
            onChange={(e) => {
              setValue(e.target.value);
              setValueError(false);
              setValueErrorMessage('');
            }}
            fullWidth
          />
          <FormControlLabel
            control={<Checkbox checked={isSensitive} onChange={(e) => setIsSensitive(e.target.checked)} />}
            label="Sensitive value"
          />
          <Stack direction="row" spacing={2}>
            <Button variant="outlined" onClick={() => navigate('/configuration/secrets')}>{t('cancel')}</Button>
            <Button variant="contained" type="submit">{t('submit')}</Button>
          </Stack>
        </Stack>
      </form>
    </Box>
  );
}

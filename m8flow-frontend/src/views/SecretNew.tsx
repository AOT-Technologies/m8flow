import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Checkbox, FormControlLabel, TextField, Button, Stack, Box, Typography } from '@mui/material';
import HttpService from '../services/HttpService';

export default function SecretNew() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');
  const [description, setDescription] = useState('');
  const [isSensitive, setIsSensitive] = useState(false);
  const [invalid, setInvalid] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!/^[\w-]+$/.test(key) || !value.trim()) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    HttpService.makeCallToBackend({
      path: '/m8flow/named-values',
      httpMethod: 'POST',
      postBody: {
        name: key,
        value,
        description: description || null,
        is_sensitive: isSensitive,
      },
      successCallback: () => navigate('/configuration/named-values'),
    });
  };

  return (
    <Box component="main" sx={{ padding: '1rem 0' }}>
      <Typography variant="h4" component="h1" gutterBottom>{t('add_secret')}</Typography>
      <form onSubmit={submit}>
        <Stack spacing={2}>
          <TextField id="secret-key" label={`${isSensitive ? t('secret_key') : 'Name'} *`} value={key} error={invalid} helperText={invalid ? t('key_alphanumeric_error') : ''} onChange={(e) => setKey(e.target.value)} fullWidth />
          {!isSensitive ? <TextField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} fullWidth /> : null}
          <TextField id="secret-value" type={isSensitive ? 'password' : 'text'} label={`${t('value')} *`} value={value} error={invalid} onChange={(e) => setValue(e.target.value)} fullWidth />
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

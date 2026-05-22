import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { MdDelete } from 'react-icons/md';
import { Can } from '@casl/react';
import PaginationForTable from '../components/PaginationForTable';
import HttpService from '../services/HttpService';
import { getPageInfoFromSearchParams } from '../helpers';
import { useUriListForPermissions } from '../hooks/UriListForPermissions';
import { PermissionsToCheck } from '../interfaces';
import { usePermissionFetcher } from '../hooks/PermissionService';
import UserService from '../services/UserService';
import { useTenants } from '../hooks/useTenants';

export default function SecretList() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [secrets, setSecrets] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [selectedTenantId, setSelectedTenantId] = useState<string>('');
  const { t } = useTranslation();

  const isSuperAdmin = UserService.isSuperAdmin();
  const { data: tenants = [] } = useTenants(isSuperAdmin);

  const { targetUris } = useUriListForPermissions();
  const permissionRequestData: PermissionsToCheck = {
    [targetUris.authenticationListPath]: ['GET'],
    [targetUris.secretListPath]: ['GET', 'POST', 'DELETE'],
  };
  const { ability, permissionsLoaded } = usePermissionFetcher(
    permissionRequestData,
  );

  const fetchSecrets = useCallback(() => {
    const setSecretsFromResult = (result: any) => {
      setSecrets(result.results);
      setPagination(result.pagination);
    };
    const { page, perPage } = getPageInfoFromSearchParams(searchParams);
    let path = `/secrets?per_page=${perPage}&page=${page}`;
    if (isSuperAdmin && selectedTenantId) {
      path += `&tenantId=${encodeURIComponent(selectedTenantId)}`;
    }
    HttpService.makeCallToBackend({
      path,
      successCallback: setSecretsFromResult,
    });
  }, [searchParams, isSuperAdmin, selectedTenantId]);

  useEffect(() => {
    if (permissionsLoaded) {
      if (
        !ability.can('GET', targetUris.secretListPath) &&
        ability.can('GET', targetUris.authenticationListPath)
      ) {
        navigate('/configuration/authentications');
      } else {
        fetchSecrets();
      }
    }
  }, [
    permissionsLoaded,
    ability,
    navigate,
    targetUris.authenticationListPath,
    targetUris.secretListPath,
    fetchSecrets,
  ]);

  const reloadSecrets = (_result: any) => {
    window.location.reload();
  };

  const handleDeleteSecret = (key: any) => {
    HttpService.makeCallToBackend({
      path: `/secrets/${key}`,
      successCallback: reloadSecrets,
      httpMethod: 'DELETE',
    });
  };

  const tenantFilterElement = () => {
    if (!isSuperAdmin || tenants.length === 0) {
      return null;
    }
    return (
      <Box sx={{ mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="secret-list-tenant-filter-label">
            {t('tenant')}
          </InputLabel>
          <Select
            labelId="secret-list-tenant-filter-label"
            label={t('tenant')}
            value={selectedTenantId}
            data-testid="secret-list-tenant-filter"
            onChange={(e) => setSelectedTenantId(e.target.value)}
          >
            <MenuItem value="">
              <em>{t('all_tenants', 'All Tenants')}</em>
            </MenuItem>
            {tenants.map((tenant) => (
              <MenuItem key={tenant.id} value={tenant.id}>
                {tenant.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>
    );
  };

  const buildTable = () => {
    const rows = secrets.map((row) => {
      const tenantName = (row as any).tenantName || (row as any).tenantId || '-';
      return (
        <TableRow key={(row as any).key}>
          <TableCell>
            <Link to={`/configuration/secrets/${(row as any).key}`}>
              {(row as any).id}
            </Link>
          </TableCell>
          <TableCell>
            <Link to={`/configuration/secrets/${(row as any).key}`}>
              {(row as any).key}
            </Link>
          </TableCell>
          <TableCell>{(row as any).username}</TableCell>
          {isSuperAdmin && (
            <TableCell data-testid="secret-list-tenant-cell">
              <Typography variant="body2">{tenantName}</Typography>
            </TableCell>
          )}
          <TableCell aria-label="Delete">
            <Can I="DELETE" a={targetUris.secretListPath} ability={ability}>
              <MdDelete onClick={() => handleDeleteSecret((row as any).key)} />
            </Can>
          </TableCell>
        </TableRow>
      );
    });
    return (
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>{t('id')}</TableCell>
              <TableCell>{t('secret_key')}</TableCell>
              <TableCell>{t('creator')}</TableCell>
              {isSuperAdmin && <TableCell>{t('tenant')}</TableCell>}
              <TableCell>{t('delete')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>{rows}</TableBody>
        </Table>
      </TableContainer>
    );
  };

  const SecretsDisplayArea = () => {
    const { page, perPage } = getPageInfoFromSearchParams(searchParams);
    let displayText = null;
    if (secrets?.length > 0) {
      displayText = (
        <PaginationForTable
          page={page}
          perPage={perPage}
          pagination={pagination as any}
          tableToDisplay={buildTable()}
        />
      );
    } else {
      displayText = <p>{t('no_secrets_to_display')}</p>;
    }
    return displayText;
  };

  if (pagination) {
    return (
      <div>
        <Typography variant="h1">{t('secrets')}</Typography>
        {tenantFilterElement()}
        {SecretsDisplayArea()}
        <Can I="POST" a={targetUris.secretListPath} ability={ability}>
          <Button
            component={Link}
            variant="contained"
            to="/configuration/secrets/new"
          >
            {t('add_a_secret')}
          </Button>
        </Can>
      </div>
    );
  }
  return null;
}

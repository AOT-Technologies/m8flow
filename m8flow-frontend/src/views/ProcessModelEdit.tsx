import { useEffect, useState } from 'react';
import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import ProcessBreadcrumb from '../components/ProcessBreadcrumb';
import ProcessModelForm from '../components/ProcessModelForm';
import { setPageTitle } from '../helpers';
import { ProcessModel } from '../interfaces';
import HttpService from '../services/HttpService';

export default function ProcessModelEdit() {
  const { t } = useTranslation();
  const params = useParams();
  const [processModel, setProcessModel] = useState<ProcessModel | null>(null);
  const processModelPath = `process-models/${params.process_model_id}`;

  useEffect(() => {
    HttpService.makeCallToBackend({
      path: `/${processModelPath}`,
      successCallback: setProcessModel,
    });
  }, [processModelPath]);

  useEffect(() => {
    if (processModel) {
      setPageTitle([
        t('editing_process_model', { name: processModel.display_name }),
      ]);
    }
  }, [processModel, t]);

  if (!processModel) {
    return null;
  }

  return (
    <Box>
      <ProcessBreadcrumb
        hotCrumbs={[
          [t('process_groups'), '/process-groups'],
          {
            entityToExplode: processModel,
            entityType: 'process-model',
            linkLastItem: true,
          },
        ]}
      />
      <Typography variant="h1">
        {`${t('edit_process_model')}: ${processModel.id}`}
      </Typography>
      <Box mt={2}>
        <ProcessModelForm
          mode="edit"
          processGroupId={params.process_group_id}
          processModel={processModel}
          setProcessModel={setProcessModel}
        />
      </Box>
    </Box>
  );
}

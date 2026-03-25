import {
  Card,
  Button,
  Stack,
  Typography,
  CardActionArea,
  CardContent,
  CardActions,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { PointerEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Subject, Subscription } from 'rxjs';
import { Can } from '@casl/react';
import { modifyProcessIdentifierForPathParam } from '../../helpers';
import { getStorageValue } from '../../services/LocalStorageService';
import { PermissionsToCheck, ProcessModel } from '../../interfaces';
import { usePermissionFetcher } from '../../hooks/PermissionService';

const defaultStyle = {
  ':hover': {
    backgroundColor: 'background.bluegreylight',
  },
  padding: 2,
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  position: 'relative',
  border: '1px solid',
  borderColor: 'borders.primary',
  borderRadius: 2,
};

/**
 * Displays the Process Model info.
 * Note that Models and Groups may seem similar, but
 * some of the event handling and stream info is different.
 * Eventually might refactor to a common component, but at this time
 * it's useful to keep them separate.
 */
export default function ProcessModelCard({
  model,
  stream,
  lastSelected,
  onStartProcess,
  onViewProcess,
}: {
  model: ProcessModel;
  stream?: Subject<Record<string, any>>;
  lastSelected?: Record<string, any>;
  onStartProcess?: () => void;
  onViewProcess?: () => void;
}) {
  const { t } = useTranslation();
  const [selectedStyle, setSelectedStyle] =
    useState<Record<string, any>>(defaultStyle);
  const [isFavorite, setIsFavorite] = useState(false);

  const navigate = useNavigate();

  const modifiedProcessModelId = modifyProcessIdentifierForPathParam(
    model.id,
  );
  const processInstanceCreatePath = `/v1.0/process-instances/${modifiedProcessModelId}`;

  const permissionRequestData: PermissionsToCheck = {
    [processInstanceCreatePath]: ['POST'],
  };
  const { ability } = usePermissionFetcher(permissionRequestData);

  const stopEventBubble = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
  };

  const handleStartProcess = (e: PointerEvent) => {
    stopEventBubble(e);
    if (onStartProcess) {
      onStartProcess();
    }
    navigate(`/${modifiedProcessModelId}/start`);
  };

  const handleViewProcess = (e: PointerEvent) => {
    stopEventBubble(e);
    if (onViewProcess) {
      onViewProcess();
    }
    navigate(`/process-models/${modifiedProcessModelId}`);
  };

  const handleClickStream = (item: Record<string, any>) => {
    if (model.id === item.id) {
      setSelectedStyle((prev) => ({
        ...prev,
        borderColor: 'primary.main',
        borderWidth: 2,
        boxShadow: 2,
      }));

      return;
    }

    setSelectedStyle({ ...defaultStyle });
  };

  useEffect(() => {
    const favorites = JSON.parse(getStorageValue('spifffavorites'));
    setIsFavorite(favorites.includes(model.id));
  }, [isFavorite, model]);

  let styleInit = false;
  useEffect(() => {
    if (!styleInit && lastSelected) {
      handleClickStream(lastSelected);
      // eslint-disable-next-line react-hooks/exhaustive-deps
      styleInit = true;
    }
  }, [lastSelected]);

  let streamSub: Subscription;
  useEffect(() => {
    if (!streamSub && stream) {
      // eslint-disable-next-line react-hooks/exhaustive-deps
      streamSub = stream.subscribe(handleClickStream);
    }

    return () => {
      streamSub.unsubscribe();
    };
  }, [stream, selectedStyle]);
  return (
    <Card
      elevation={0}
      sx={selectedStyle}
      onClick={(e) => handleViewProcess(e as unknown as PointerEvent)}
      id={`card-${modifyProcessIdentifierForPathParam(model.id)}`}
    >
      <CardActionArea>
        <CardContent>
          <Stack gap={1} sx={{ height: '100%' }}>
            <Typography
              variant="body2"
              sx={{ fontWeight: 700 }}
              data-testid={`process-model-card-${model.display_name}`}
            >
              {model.display_name}
            </Typography>
            <Typography
              variant="caption"
              sx={{ fontWeight: 700, color: 'text.secondary' }}
            >
              {model.description || '--'}
            </Typography>
          </Stack>
        </CardContent>
      </CardActionArea>
      <Can I="POST" a={processInstanceCreatePath} ability={ability}>
        <CardActions sx={{ mt: 'auto', p: 2 }}>
          <Button
            variant="contained"
            color="primary"
            size="small"
            onClick={(e) => handleStartProcess(e as unknown as PointerEvent)}
          >
            {t('start_process')}
          </Button>
        </CardActions>
      </Can>
    </Card>
  );
}

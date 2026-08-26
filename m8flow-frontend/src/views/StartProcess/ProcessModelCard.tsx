import {
  Box,
  Button,
  Card,
  CardActionArea,
  CardActions,
  CardContent,
  Chip,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { PointerEvent, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Subject, Subscription } from 'rxjs';
import { ProcessModel } from '../../interfaces';
import { modifyProcessIdentifierForPathParam } from '../../helpers';
import { getStorageValue } from '../../services/LocalStorageService';
import UserService from '../../services/UserService';
import { getProcessTenantLabel } from './processTenantLabelRegistry';

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

type ProcessModelCardProps = {
  model: ProcessModel & { tenantName?: string };
  stream?: Subject<Record<string, any>>;
  lastSelected?: Record<string, any>;
  onStartProcess?: () => void;
  onViewProcess?: () => void;
  disableStartProcess?: boolean;
  disabledReason?: string;
};

export default function ProcessModelCard({
  model,
  stream,
  lastSelected,
  onStartProcess,
  onViewProcess,
  disableStartProcess = false,
  disabledReason = '',
}: ProcessModelCardProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [selectedStyle, setSelectedStyle] =
    useState<Record<string, any>>(defaultStyle);
  const [isFavorite, setIsFavorite] = useState(false);
  const didInitSelectionRef = useRef(false);
  const tenantLabel = model.tenantName || getProcessTenantLabel(model.id);
  const showTenantChip = UserService.isSuperAdmin() && Boolean(tenantLabel);

  const stopEventBubble = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
  };

  const handleStartProcess = (e: PointerEvent) => {
    stopEventBubble(e);
    if (disableStartProcess) {
      return;
    }
    onStartProcess?.();
    navigate(`/${modifyProcessIdentifierForPathParam(model.id)}/start`);
  };

  const handleViewProcess = (e: PointerEvent) => {
    stopEventBubble(e);
    onViewProcess?.();
    navigate(`/process-models/${modifyProcessIdentifierForPathParam(model.id)}`);
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
  }, [isFavorite, model.id]);

  useEffect(() => {
    if (!didInitSelectionRef.current && lastSelected) {
      handleClickStream(lastSelected);
      didInitSelectionRef.current = true;
    }
  }, [lastSelected]);

  useEffect(() => {
    let streamSubscription: Subscription | undefined;
    if (stream) {
      streamSubscription = stream.subscribe(handleClickStream);
    }

    return () => {
      streamSubscription?.unsubscribe();
    };
  }, [stream]);

  const card = (
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
      <CardActions sx={{ mt: 'auto', p: 2 }}>
        <Tooltip title={disableStartProcess ? disabledReason : ''}>
          <span>
            <Button
              variant="contained"
              color="primary"
              size="small"
              onClick={(e) => handleStartProcess(e as unknown as PointerEvent)}
              disabled={disableStartProcess}
              data-testid={`start-process-button-${model.id}`}
            >
              {t('start_process')}
            </Button>
          </span>
        </Tooltip>
      </CardActions>
    </Card>
  );

  if (!showTenantChip) {
    return card;
  }

  return (
    <Box sx={{ position: 'relative', height: '100%' }}>
      <Chip
        size="small"
        label={tenantLabel}
        data-testid={`process-model-tenant-chip-${model.id}`}
        sx={{ position: 'absolute', top: 12, right: 12, zIndex: 1 }}
      />
      {card}
    </Box>
  );
}

import {
  Card,
  Button,
  Stack,
  Typography,
  CardActionArea,
  CardContent,
  CardActions,
  Chip,
  Box,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { PointerEvent } from 'react';
import { TimeAgo } from '@spiffworkflow-frontend/helpers/timeago';
import DateAndTimeService from '@spiffworkflow-frontend/services/DateAndTimeService';
import { Template, TemplateVisibility } from '../types/template';

interface TemplateCardProps {
  template: Template;
  onUseTemplate?: () => void;
  onViewTemplate?: () => void;
}

const getVisibilityColor = (visibility: TemplateVisibility): 'default' | 'primary' | 'secondary' => {
  switch (visibility) {
    case 'PUBLIC':
      return 'primary';
    case 'TENANT':
      return 'secondary';
    case 'PRIVATE':
    default:
      return 'default';
  }
};

const getVisibilityLabel = (visibility: TemplateVisibility): string => {
  switch (visibility) {
    case 'PUBLIC':
      return 'Public';
    case 'TENANT':
      return 'Tenant';
    case 'PRIVATE':
    default:
      return 'Private';
  }
};

export default function TemplateCard({
  template,
  onUseTemplate,
  onViewTemplate,
}: TemplateCardProps) {
  const navigate = useNavigate();

  const stopEventBubble = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
  };

  const handleUseTemplate = (e: PointerEvent) => {
    stopEventBubble(e);
    if (onUseTemplate) {
      onUseTemplate();
    }
    // Navigate to template detail or start process page
    navigate(`/templates/${template.id}`);
  };

  const handleViewTemplate = (e: PointerEvent) => {
    stopEventBubble(e);
    if (onViewTemplate) {
      onViewTemplate();
    }
    navigate(`/templates/${template.id}`);
  };

  return (
    <Card
      elevation={0}
      sx={{
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
      }}
      onClick={(e) => handleViewTemplate(e as unknown as PointerEvent)}
      id={`template-card-${template.id}`}
    >
      <CardActionArea>
        <CardContent>
          <Stack gap={1} sx={{ height: '100%' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Typography
                variant="body2"
                sx={{ fontWeight: 700 }}
                data-testid={`template-card-${template.name}`}
              >
                {template.name}
              </Typography>
              <Chip
                label={getVisibilityLabel(template.visibility)}
                color={getVisibilityColor(template.visibility)}
                size="small"
                sx={{ ml: 1 }}
              />
            </Box>
            <Typography
              variant="caption"
              sx={{ fontWeight: 700, color: 'text.secondary' }}
            >
              {template.description || '--'}
            </Typography>
            {template.category && (
              <Chip
                label={`Category: ${template.category}`}
                size="small"
                variant="outlined"
                sx={{ alignSelf: 'flex-start', fontSize: '0.7rem' }}
              />
            )}
            {template.tags && template.tags.length > 0 && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                {template.tags.slice(0, 3).map((tag, index) => (
                  <Chip
                    key={index}
                    label={tag}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: '0.7rem' }}
                  />
                ))}
                {template.tags.length > 3 && (
                  <Chip
                    label={`+${template.tags.length - 3}`}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: '0.7rem' }}
                  />
                )}
              </Box>
            )}
            <Typography variant="caption" sx={{ color: 'text.secondary', mt: 'auto' }}>
              Version: {template.version}
            </Typography>
            <Typography
              variant="caption"
              sx={{ color: 'text.secondary' }}
              title={
                DateAndTimeService.convertSecondsToFormattedDateTime(template.updatedAtInSeconds) ?? undefined
              }
            >
              Updated {TimeAgo.inWords(template.updatedAtInSeconds)}
            </Typography>
          </Stack>
        </CardContent>
      </CardActionArea>
      <CardActions sx={{ mt: 'auto', p: 2 }}>
        {/* <Button
          variant="contained"
          color="primary"
          size="small"
          onClick={(e) => handleUseTemplate(e as unknown as PointerEvent)}
        >
          Use Template
        </Button> */}
      </CardActions>
    </Card>
  );
}

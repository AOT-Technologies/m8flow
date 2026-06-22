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
  Tooltip,
  IconButton,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import RestoreIcon from '@mui/icons-material/Restore';
import { useNavigate } from 'react-router-dom';
import { useState, PointerEvent, MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { TimeAgo } from '@spiffworkflow-frontend/helpers/timeago';
import DateAndTimeService from '@spiffworkflow-frontend/services/DateAndTimeService';
import { Template, TemplateVisibility } from '../types/template';

interface TemplateCardProps {
  template: Template;
  onUseTemplate?: () => void;
  onViewTemplate?: () => void;
  showTenantContext?: boolean;
  onDeleteTemplate?: () => void;
  onRestoreTemplate?: () => void;
  onEditTemplate?: () => void;
  onDuplicateTemplate?: () => void;
  onExportTemplate?: () => void;
  deleteDisabled?: boolean;
  deleteDisabledReason?: string;
  restoreDisabled?: boolean;
  restoreDisabledReason?: string;
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

const getVisibilityLabel = (visibility: TemplateVisibility, t: any): string => {
  switch (visibility) {
    case 'PUBLIC':
      return t("public");
    case 'TENANT':
      return t("tenant");
    case 'PRIVATE':
    default:
      return t("private");
  }
};

export default function TemplateCard({
  template,
  onUseTemplate,
  onViewTemplate,
  showTenantContext = false,
  onDeleteTemplate,
  onRestoreTemplate,
  onEditTemplate,
  onDuplicateTemplate,
  onExportTemplate,
  deleteDisabled = false,
  deleteDisabledReason,
  restoreDisabled = false,
  restoreDisabledReason,
}: TemplateCardProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const menuOpen = Boolean(menuAnchor);

  const stopEventBubble = (e: PointerEvent | MouseEvent) => {
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

  const tenantDisplayValue =
    template.tenant?.name || template.tenant?.slug || template.tenantId || '--';

  const handleMenuOpen = (e: MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    e.preventDefault();
    setMenuAnchor(e.currentTarget);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
  };

  // Determine whether to show the overflow menu at all
  const hasOverflowActions =
    onDeleteTemplate || onRestoreTemplate || onEditTemplate || onDuplicateTemplate || onExportTemplate;

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
      data-testid={`template-card-${template.id}`}
    >
      <CardActionArea>
        <CardContent>
          <Stack gap={1} sx={{ height: '100%' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Typography
                variant="body2"
                sx={{ fontWeight: 700, minWidth: 0, overflowWrap: 'anywhere', wordBreak: 'break-word' }}
                data-testid={`template-card-${template.name}`}
              >
                {template.name}
              </Typography>
              <Chip
                label={getVisibilityLabel(template.visibility, t)}
                color={getVisibilityColor(template.visibility)}
                size="small"
                sx={{ ml: 1, flexShrink: 0 }}
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
                label={`${t("category")}: ${template.category}`}
                size="small"
                variant="outlined"
                sx={{ alignSelf: 'flex-start', fontSize: '0.7rem' }}
              />
            )}
            {template.tags && template.tags.length > 0 && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                {template.tags.slice(0, 3).map((tag) => (
                  <Chip
                    key={tag}
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
              {t("version")}: {template.version}
            </Typography>
            {showTenantContext && (
              <>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {t('tenant')}: {tenantDisplayValue}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {t("owner_label", { owner: template.createdBy || '--' })}
                </Typography>
              </>
            )}
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
      <CardActions sx={{ mt: 'auto', p: 2, gap: 1, justifyContent: 'flex-end' }}>
        {hasOverflowActions && (
          <>
            <IconButton
              size="small"
              onClick={handleMenuOpen}
              aria-label={t("more_actions", { defaultValue: "More actions" })}
              data-testid={`template-card-more-actions-${template.id}`}
              sx={{
                border: '1px solid',
                borderColor: 'borders.primary',
                borderRadius: 1,
              }}
            >
              <MoreVertIcon fontSize="small" />
            </IconButton>
            <Menu
              anchorEl={menuAnchor}
              open={menuOpen}
              onClose={handleMenuClose}
              onClick={(e) => e.stopPropagation()}
              anchorOrigin={{
                vertical: 'bottom',
                horizontal: 'right',
              }}
              transformOrigin={{
                vertical: 'top',
                horizontal: 'right',
              }}
              data-testid={`template-card-actions-menu-${template.id}`}
            >
              {onEditTemplate && (
                <MenuItem
                  onClick={() => {
                    handleMenuClose();
                    onEditTemplate();
                  }}
                  data-testid={`template-card-edit-${template.id}`}
                >
                  <ListItemIcon>
                    <EditIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText>{t("edit", { defaultValue: "Edit" })}</ListItemText>
                </MenuItem>
              )}
              {onDuplicateTemplate && (
                <MenuItem
                  onClick={() => {
                    handleMenuClose();
                    onDuplicateTemplate();
                  }}
                  data-testid={`template-card-duplicate-${template.id}`}
                >
                  <ListItemIcon>
                    <ContentCopyIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText>{t("duplicate", { defaultValue: "Duplicate" })}</ListItemText>
                </MenuItem>
              )}
              {onExportTemplate && (
                <MenuItem
                  onClick={() => {
                    handleMenuClose();
                    onExportTemplate();
                  }}
                  data-testid={`template-card-export-${template.id}`}
                >
                  <ListItemIcon>
                    <FileDownloadIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText>{t("export", { defaultValue: "Export" })}</ListItemText>
                </MenuItem>
              )}
              {onRestoreTemplate && (
                <Tooltip title={restoreDisabled ? (restoreDisabledReason || "") : ""}>
                  <span>
                    <MenuItem
                      onClick={() => {
                        handleMenuClose();
                        onRestoreTemplate();
                      }}
                      disabled={restoreDisabled}
                      data-testid={`template-card-restore-${template.id}`}
                    >
                      <ListItemIcon>
                        <RestoreIcon fontSize="small" />
                      </ListItemIcon>
                      <ListItemText>{t("restore", { defaultValue: "Restore" })}</ListItemText>
                    </MenuItem>
                  </span>
                </Tooltip>
              )}
              {onDeleteTemplate && (
                <Tooltip title={deleteDisabled ? (deleteDisabledReason || "") : ""}>
                  <span>
                    <MenuItem
                      onClick={() => {
                        handleMenuClose();
                        onDeleteTemplate();
                      }}
                      disabled={deleteDisabled}
                      data-testid={`template-card-delete-${template.id}`}
                      sx={{ color: 'error.main' }}
                    >
                      <ListItemIcon>
                        <DeleteIcon fontSize="small" color="error" />
                      </ListItemIcon>
                      <ListItemText>{t("delete")}</ListItemText>
                    </MenuItem>
                  </span>
                </Tooltip>
              )}
            </Menu>
          </>
        )}
      </CardActions>
    </Card>
  );
}

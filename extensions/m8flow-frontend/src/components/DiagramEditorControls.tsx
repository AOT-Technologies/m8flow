import React from 'react';
import { IconButton } from '@mui/material';
import {
  ZoomIn,
  ZoomOut,
  CenterFocusStrongOutlined,
} from '@mui/icons-material';
import SpiffTooltip from '@spiffworkflow-frontend/components/SpiffTooltip';
import { useTranslation } from 'react-i18next';

export type DiagramEditorControlsProps = {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomFit: () => void;
};

export default function DiagramEditorControls({
  onZoomIn,
  onZoomOut,
  onZoomFit,
}: DiagramEditorControlsProps) {
  const { t } = useTranslation();

  return (
    <div className="diagram-control-buttons">
      <SpiffTooltip title={t('diagram_zoom_in')} placement="bottom">
        <IconButton aria-label={t('diagram_zoom_in')} onClick={onZoomIn}>
          <ZoomIn />
        </IconButton>
      </SpiffTooltip>
      <SpiffTooltip title={t('diagram_zoom_out')} placement="bottom">
        <IconButton aria-label={t('diagram_zoom_out')} onClick={onZoomOut}>
          <ZoomOut />
        </IconButton>
      </SpiffTooltip>
      <SpiffTooltip title={t('diagram_zoom_fit')} placement="bottom">
        <IconButton aria-label={t('diagram_zoom_fit')} onClick={onZoomFit}>
          <CenterFocusStrongOutlined />
        </IconButton>
      </SpiffTooltip>
    </div>
  );
}

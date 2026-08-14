// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// Zoom control strip for the diagram editor. The `diagram-control-buttons` class and
// the `diagram_zoom_*` translation keys are contracts with the shared stylesheet and
// locale bundles, so they are named verbatim; the markup itself is generated from one
// descriptor list rather than repeated per button.

import type { ComponentType } from 'react';
import { IconButton } from '@mui/material';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import CenterFocusStrongOutlinedIcon from '@mui/icons-material/CenterFocusStrongOutlined';
import SpiffTooltip from '@spiffworkflow-frontend/components/SpiffTooltip';
import { useTranslation } from 'react-i18next';

export type DiagramEditorControlsProps = {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomFit: () => void;
};

type ZoomControl = {
  // Slug shared by the test id (`diagram-zoom-<slug>-button`) and the locale key
  // (`diagram_zoom_<slug>`), so a control cannot drift between the two.
  slug: 'in' | 'out' | 'fit';
  Icon: ComponentType;
  activate: () => void;
};

export default function DiagramEditorControls(props: DiagramEditorControlsProps) {
  const { t } = useTranslation();

  const controls: ZoomControl[] = [
    { slug: 'in', Icon: ZoomInIcon, activate: props.onZoomIn },
    { slug: 'out', Icon: ZoomOutIcon, activate: props.onZoomOut },
    { slug: 'fit', Icon: CenterFocusStrongOutlinedIcon, activate: props.onZoomFit },
  ];

  return (
    <div className="diagram-control-buttons">
      {controls.map(({ slug, Icon, activate }) => {
        const label = t(`diagram_zoom_${slug}`);
        return (
          <SpiffTooltip key={slug} title={label} placement="bottom">
            <IconButton
              data-testid={`diagram-zoom-${slug}-button`}
              aria-label={label}
              onClick={activate}
            >
              <Icon />
            </IconButton>
          </SpiffTooltip>
        );
      })}
    </div>
  );
}

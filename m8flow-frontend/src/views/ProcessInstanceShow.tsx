/**
 * Process instance show — upstream page, m8flow info-header layout.
 *
 * M8F-370: upstream stacks the instance summary (status / started by / started /
 * completed / last milestone / revision) vertically in a half-width column. We
 * want it spread across the full width as a column grid. Done purely by
 * restyling upstream's markup — `display: contents` on the two MUI Grid items
 * promotes their `<dl>` children into our own grid — so no upstream body is
 * copied here.
 */
import type { ComponentProps } from 'react';
import { Box } from '@mui/material';
import UpstreamProcessInstanceShow from '@spiff-core/views/ProcessInstanceShow';

export default function ProcessInstanceShow(
  props: ComponentProps<typeof UpstreamProcessInstanceShow>,
) {
  return (
    <Box
      sx={{
        '& > .MuiGrid-container:has([data-testid="process-instance-status-chip"])':
          {
            display: 'grid',
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(0, 1fr))',
              lg: 'repeat(4, minmax(0, 1fr))',
            },
            columnGap: 3,
            rowGap: 0,
            // Upstream's two Grid columns become transparent, so every <dl>
            // inside them (summary fields first, then metadata) is a grid cell.
            '& > .MuiGrid-root': { display: 'contents' },
          },
      }}
    >
      <UpstreamProcessInstanceShow {...props} />
    </Box>
  );
}

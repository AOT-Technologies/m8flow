// @ts-nocheck
/**
 * M8Flow process instance NavigatedViewer — camunda-bpmn-js shaped.
 *
 * Host:
 *   import NavigatedViewer, { applyTaskStateMarkers } from 'm8flow-bpmn/lib/NavigatedViewer';
 *   const viewer = new NavigatedViewer({ container });
 *   await viewer.importXML(xml);
 *   applyTaskStateMarkers(viewer, tasks);
 */
import inherits from 'inherits-browser';
import BpmnNavigatedViewer from 'bpmn-js/lib/NavigatedViewer';

import 'bpmn-js/dist/assets/diagram-js.css';
import 'bpmn-js/dist/assets/bpmn-js.css';
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css';
import './assets/viewer.css';

import { addCallActivityDrilldowns } from './features/callActivityDrilldown';
import { customRendererModule } from './features/customRenderer';
import { applyTaskStateMarkers, taskStateLegendModule } from './features/taskState';
import { zoomControlsModule } from './features/zoomControls';

export type { BpmnInstanceTask } from './features/taskState';
export { addCallActivityDrilldowns, applyTaskStateMarkers };

/**
 * @param {import('bpmn-js/lib/BaseViewer').BaseViewerOptions} [options]
 */
export default function NavigatedViewer(options: Record<string, any> = {}) {
  BpmnNavigatedViewer.call(this, {
    ...options,
    // Viewer default; caller flags still win.
    m8flowRenderer: { neutralEndEvents: true, ...options.m8flowRenderer },
  });
  const container = this.get('canvas').getContainer();
  // m8flow-bpmn--viewer: hosts embed the viewer below the fold, so its
  // zoom pill sits at the top (zoom-controls.css).
  container.classList.add('m8flow-bpmn', 'm8flow-bpmn--viewer');
}

inherits(NavigatedViewer, BpmnNavigatedViewer);

NavigatedViewer.prototype._m8flowModules = [
  customRendererModule,
  zoomControlsModule,
  taskStateLegendModule,
];

NavigatedViewer.prototype._modules = [].concat(
  BpmnNavigatedViewer.prototype._modules,
  NavigatedViewer.prototype._m8flowModules,
);

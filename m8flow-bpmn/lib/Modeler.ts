// @ts-nocheck
/**
 * M8Flow/Spiff BPMN Modeler distribution — camunda-bpmn-js shaped.
 *
 * Host:
 *   import Modeler from 'm8flow-bpmn/lib/Modeler';
 *   import 'm8flow-bpmn/dist/assets/modeler.css'; // optional; also imported here
 *   new Modeler({ container, propertiesPanel: { parent }, keyboard: { bindTo: document } });
 */
import inherits from 'inherits-browser';
import BpmnModeler from 'bpmn-js/lib/Modeler';
import {
  BpmnPropertiesPanelModule,
  BpmnPropertiesProviderModule,
  // @ts-expect-error missing type declarations
} from 'bpmn-js-properties-panel';
// @ts-expect-error missing type declarations
import spiffworkflow from 'bpmn-js-spiffworkflow/app/spiffworkflow';
import spiffModdleExtension from 'bpmn-js-spiffworkflow/app/spiffworkflow/moddle/spiffworkflow.json';

import 'bpmn-js/dist/assets/diagram-js.css';
import 'bpmn-js/dist/assets/bpmn-js.css';
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css';
import 'bpmn-js-spiffworkflow/app/css/app.css';
import '@bpmn-io/properties-panel/assets/properties-panel.css';
import './assets/modeler.css';

import { customPaletteModule } from './features/customPalette';
import { customRendererModule } from './features/customRenderer';
import { droppedConstructReplaceFilterModule } from './features/droppedConstructCreate';
import { droppedConstructPanelModule } from './features/droppedConstructPanel';
import { externalFormPropertiesModule } from './features/externalFormPropertiesProvider';
import {
  createPrePostScriptOverlay,
  fixUnresolvedReferences,
  positionContextPadAboveTarget,
} from './features/modelerBehaviors';
import { serviceTaskConnectorPanelModule } from './features/serviceTaskConnectorPanel';
import { taskSizingModule } from './features/taskSizingBehavior';
import { zoomControlsModule } from './features/zoomControls';

/**
 * @param {import('bpmn-js/lib/BaseViewer').BaseViewerOptions} [options]
 */
export default function Modeler(options: Record<string, any> = {}) {
  options = {
    ...options,
    moddleExtensions: {
      spiffworkflow: spiffModdleExtension,
      ...options.moddleExtensions,
    },
  };

  BpmnModeler.call(this, options);

  fixUnresolvedReferences(this);
  positionContextPadAboveTarget(this);
  this.on('shape.added', (event: any) => createPrePostScriptOverlay(this, event));

  const container = this.get('canvas').getContainer();
  container.classList.add('m8flow-bpmn');
}

inherits(Modeler, BpmnModeler);

Modeler.prototype._m8flowModules = [
  spiffworkflow,
  externalFormPropertiesModule,
  // Must register after `spiffworkflow` — it finds-and-replaces the
  // `service_task_properties` group spiffworkflow's own provider already
  // pushed (same "runs later in the getGroups middleware chain" trick
  // externalFormPropertiesModule uses above).
  serviceTaskConnectorPanelModule,
  BpmnPropertiesPanelModule,
  BpmnPropertiesProviderModule,
  customPaletteModule,
  customRendererModule,
  droppedConstructReplaceFilterModule,
  // After Spiff panel groups: strip dropped-construct editors and, when a
  // leftover dropped shape is selected, show a short "not supported" notice.
  droppedConstructPanelModule,
  // After customPaletteModule: palette injects `elementFactory`, so the
  // sizing override must win in DI resolution.
  taskSizingModule,
  zoomControlsModule,
];

Modeler.prototype._modules = [].concat(
  BpmnModeler.prototype._modules,
  Modeler.prototype._m8flowModules,
);

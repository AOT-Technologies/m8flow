// @ts-nocheck
/**
 * M8Flow DMN Modeler distribution — camunda-bpmn-js shaped (stock dmn-js
 * chrome plus BPMN-matching DRD zoom; no DMN mockup). Host supplies
 * container + properties panel parent.
 *
 *   import DmnModeler from 'm8flow-bpmn/lib/DmnModeler';
 *   new DmnModeler({
 *     container,
 *     propertiesPanel: { parent },
 *     keyboard: { bindTo: document },
 *   });
 */
import inherits from 'inherits-browser';
import BaseDmnModeler from 'dmn-js/lib/Modeler';
import {
  DmnPropertiesPanelModule,
  DmnPropertiesProviderModule,
} from 'dmn-js-properties-panel';

import { zoomControlsModule } from './features/zoomControls';

import 'dmn-js/dist/assets/diagram-js.css';
import 'dmn-js/dist/assets/dmn-js-decision-table-controls.css';
import 'dmn-js/dist/assets/dmn-js-decision-table.css';
import 'dmn-js/dist/assets/dmn-js-drd.css';
import 'dmn-js/dist/assets/dmn-js-literal-expression.css';
import 'dmn-js/dist/assets/dmn-js-shared.css';
import 'dmn-js/dist/assets/dmn-font/css/dmn-embedded.css';
import '@bpmn-io/properties-panel/assets/properties-panel.css';
import './assets/dmn.css';

/**
 * @param {Record<string, any>} [options]
 */
export default function DmnModeler(options = {}) {
  const { propertiesPanel, drd, ...rest } = options;
  const merged = {
    ...rest,
    drd: {
      ...drd,
      propertiesPanel: drd?.propertiesPanel ?? propertiesPanel,
      additionalModules: [
        DmnPropertiesPanelModule,
        DmnPropertiesProviderModule,
        zoomControlsModule,
        ...(drd?.additionalModules ?? []),
      ],
    },
  };

  BaseDmnModeler.call(this, merged);
}

inherits(DmnModeler, BaseDmnModeler);

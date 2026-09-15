# m8flow-bpmn

Embeddable M8Flow/Spiff modeling distributions based on [bpmn-js](https://github.com/bpmn-io/bpmn-js), shaped like [camunda-bpmn-js](https://github.com/camunda/camunda-bpmn-js).

Private `file:` package for `m8flow-designer`. No React — hosts supply thin shells.

## Install (designer)

```json
"m8flow-bpmn": "file:../m8flow-bpmn"
```

## Usage

```js
import Modeler from 'm8flow-bpmn/lib/Modeler';
import NavigatedViewer, { applyTaskStateMarkers } from 'm8flow-bpmn/lib/NavigatedViewer';
import DmnModeler from 'm8flow-bpmn/lib/DmnModeler';
import 'm8flow-bpmn/dist/assets/modeler.css'; // optional; also imported by Modeler
import m8flowBpmnVitePlugin from 'm8flow-bpmn/vite';

const modeler = new Modeler({
  container: '#canvas',
  propertiesPanel: { parent: '#properties' },
  keyboard: { bindTo: document },
});

await modeler.importXML(xml);
```

Vite host config:

```js
import m8flowBpmnVitePlugin from 'm8flow-bpmn/vite';
const m8flowBpmn = m8flowBpmnVitePlugin();

export default defineConfig({
  plugins: [react(), ...m8flowBpmn.plugins],
  resolve: { alias: { '@': ..., ...m8flowBpmn.resolve.alias } },
  optimizeDeps: m8flowBpmn.optimizeDeps,
});
```

## Test

```sh
npm test
```

Vitest covers pure helpers. `vite-node` smoke checks public exports resolve. Full diagram render coverage is designer Playwright e2e (jsdom cannot run diagram-js).

## Public exports

| Path | What |
| --- | --- |
| `lib/Modeler` | Process modeler (Spiff, panel, custom renderer/palette, zoom) |
| `lib/NavigatedViewer` | Process instance viewer (renderer, zoom, task-state legend) |
| `lib/DmnModeler` | DMN modeler (stock dmn-js chrome + panel) |
| `vite` | Preact alias + Spiff JSX plugin |
| `dist/assets/modeler.css` / `viewer.css` / `dmn.css` | Package chrome CSS |

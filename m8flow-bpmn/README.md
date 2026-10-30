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

## Translation

Every UI string goes through the diagram-js `translate` service, with the English text as the key. Hosts override it and fire `i18n.changed` when the language changes; the palette, an open context pad, the properties panel, zoom controls and task-state legend re-render on that event. `canvasI18n` and `propertiesPanelI18n` also route text that bpmn-js-spiffworkflow and dmn-js-properties-panel hardcode (group headers, entry labels, "Launch Editor", the IoPalette titles) through `translate`.

```js
const translateModule = { translate: ['value', (template, replacements) => lookup(template, replacements)] };

new Modeler({ ...options, additionalModules: [translateModule] });
new NavigatedViewer({ ...options, additionalModules: [translateModule] });
// dmn-js ignores `common.additionalModules`, so pass it per view.
new DmnModeler({ ...options, drd: { additionalModules: [translateModule] }, decisionTable: { additionalModules: [translateModule] } });

modeler.get('eventBus').fire('i18n.changed');
```

The designer's implementation and dictionaries: `m8flow-designer/src/lib/diagramI18n.ts`, `m8flow-designer/src/locales/<lng>/diagram.json`.

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

# camunda-bpmn-js-behaviors

[![CI](https://github.com/camunda/camunda-bpmn-js-behaviors/workflows/CI/badge.svg)](https://github.com/camunda/camunda-bpmn-js-behaviors/actions?query=workflow%3ACI)


Behaviors for [bpmn-js](https://github.com/bpmn-io/bpmn-js) ensuring that parts of the model that are specific to Camunda 7 and 8 are maintained. For example, the Camunda 8 behaviors will ensure that a `bpmn:BusinessRuleTask` element will not have a `zeebe:CalledDecision` and `zeebe:TaskDefinition` extension element at the same time.

## Usage

### Camunda 7

```js
import camundaPlatformBehaviors from 'camunda-bpmn-js-behaviors/lib/camunda-platform';

const bpmnModeler = new BpmnModeler({
  container: '#container',
  additionalModules: [
    camundaPlatformBehaviors
  ]
});

bpmnModeler.importXML('...');
```

### Camunda 8

```js
import camundaCloudBehaviors from 'camunda-bpmn-js-behaviors/lib/camunda-cloud';

const bpmnModeler = new BpmnModeler({
  container: '#container',
  additionalModules: [
    camundaCloudBehaviors
  ]
});

bpmnModeler.importXML('...');
```

## Development Setup

Prepare the project by installing all dependencies:

```sh
npm install
```

Then, depending on your use-case, you may run any of the following commands:

```sh
# lint and run tests once
npm run all

# run the tests in watch mode
npm run dev
```

## License

MIT

Uses [bpmn-js](https://github.com/bpmn-io/bpmn-js) licensed under the bpmn.io license.

# Camunda FEEL Builtins

Collection of builtin Camunda extensions for FEEL (Friendly Enough Expression Language). These builtins get extracted from [camunda-docs](https://github.com/camunda/camunda-docs/tree/main/docs/components/modeler/feel/builtin-functions).

## Installation

Install via npm:

```sh
npm install @camunda/feel-builtins
```

## Usage

### Feel Editor

In your [FEEL editor](https://github.com/bpmn-io/feel-editor) you can use these builtins to establish the Camunda context:

```js
import { camundaBuiltins } from '@camunda/feel-builtins';
import FeelEditor from '@bpmn-io/feel-editor';

const editor = new FeelEditor({
  container,
  builtins: camundaBuiltins,
  parserDialect: 'camunda'
});
```

### Feel Lint

With [@bpmn-io/feel-lint](https://github.com/bpmn-io/feel-lint) you can also use the builtins to lint expressions in the Camunda world:

```js
import { camundaBuiltins } from '@camunda/feel-builtins';
import { lintExpression } from '@bpmn-io/feel-lint';

lintExpression(expression, {
  builtins: camundaBuiltins,
  parserDialect: 'camunda'
});
```

## Resources

* [Changelog](./CHANGELOG.md)
* [Issues](https://github.com/camunda/feel-builtins/issues)

## Build and Run  

Prepare the project by installing dependencies:

```sh
npm install
```

Then, depending on your use-case you may run any of the following commands:

```sh
# lint the library and run all tests
npm run all

# update the built-ins from latest camunda-docs
npm run update-builtins
```

## Related

* [@bpmn-io/feel-editor](https://github.com/bpmn-io/feel-editor): FEEL editor and playground
* [@bpmn-io/feel-lint](https://github.com/bpmn-io/feel-lint): A linter for FEEL expressions

## License

[MIT](./LICENSE)

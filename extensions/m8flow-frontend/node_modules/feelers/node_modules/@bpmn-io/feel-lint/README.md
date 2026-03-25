# @bpmn-io/feel-lint

[![CI](https://github.com/bpmn-io/feel-lint/actions/workflows/CI.yml/badge.svg)](https://github.com/bpmn-io/feel-lint/actions/workflows/CI.yml)

Linting for FEEL expressions.

## Usage

There are 2 ways to use this library:

### Linting string expressions

The `lintExpression` function takes a string expression and returns a list of linting errors.

```javascript
import { lintExpression } from "@bpmn-io/feel-lint"

lintExpression('foo = bar');
```

You may pass custom language configuration to the editor:

```javascript
lintExpression('> 10, "yes", mike\'s name', {
  dialect: 'unaryTests',
  context: {
    "mike's name": "Mike the might"
  }
});
```

### CodeMirror plugin

The `cmFeelLinter` function returns a [`LintSource`](https://codemirror.net/docs/ref/#lint.LintSource) that you can use to extend your [CodeMirror](https://codemirror.net/) instance.

```javascript
import { cmFeelLinter } from "@bpmn-io/feel-lint"
import { linter } from '@codemirror/lint';

// ...

const myEditor = new EditorView({
    state: EditorState.create({
      doc: '',
      extensions: [
        linter(cmFeelLinter())
      ]
    })
  });
```


## Hacking the Project

To get the development setup make sure to have [NodeJS](https://nodejs.org/en/download/) installed.
As soon as you are set up, clone the project and execute

```
npm install
npm run dev
```

## License

MIT

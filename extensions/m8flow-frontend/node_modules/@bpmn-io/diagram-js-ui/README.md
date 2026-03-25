# diagram-js-ui

[![CI](https://github.com/bpmn-io/diagram-js-ui/actions/workflows/CI.yml/badge.svg)](https://github.com/bpmn-io/diagram-js-ui/actions/workflows/CI.yml)

A wrapper around [`htm/preact`](https://github.com/developit/htm#usage) that exposes components for building reactive HTML widgets in the context of [diagram-js](https://github.com/bpmn-io/diagram-js) and extensions.


## Usage

This module is available through `diagram-js/lib/ui`. Use it to create and mount your [Preact](https://preactjs.com/) components and render them through the [`htm` utility](https://github.com/developit/htm).

```javascript
// MyService.js
import { render, html } from 'diagram-js/lib/ui';
import MyCounter from './MyCounter';

export default function MyService() {
  const parentElement = document.createElement('div');

  render(html`<${MyCounter} />`, parentElement);
}
```

```javascript
// MyCounter.js
import { useState, html } from 'diagram-js/lib/ui';

export default function MyCounter(props) {
  const counter = useState(0);

  return html`
    <div>Counter: ${counter}</div>
  `;
}
```


## Build and Run

```sh
# install all dependencies
npm install

# lint and build the library
npm run all
```


## License

MIT

# inherits-browser

A [inherits@2](https://www.npmjs.com/package/inherits) fork that is safe per default to use in browsers.


## Usage

```javascript
import inherits from 'inherits-browser';

function Parent() {}

function Child() {
  Parent.call(this);
}

inherits(Child, Parent);
```


## Why

* Do not require `package.json#browser`; always be browser compatible
* Target modern run-times (IE9+, other browsers + NodeJS) only

## License

ISC
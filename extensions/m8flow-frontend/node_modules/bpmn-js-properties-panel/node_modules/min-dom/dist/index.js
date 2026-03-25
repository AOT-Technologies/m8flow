import { forEach } from 'min-dash';
export { default as domify } from 'domify';

function _mergeNamespaces(n, m) {
  m.forEach(function (e) {
    e && typeof e !== 'string' && !Array.isArray(e) && Object.keys(e).forEach(function (k) {
      if (k !== 'default' && !(k in n)) {
        var d = Object.getOwnPropertyDescriptor(e, k);
        Object.defineProperty(n, k, d.get ? d : {
          enumerable: true,
          get: function () { return e[k]; }
        });
      }
    });
  });
  return Object.freeze(n);
}

/**
 * Assigns style attributes in a style-src compliant way.
 *
 * @param {Element} element
 * @param {...Object} styleSources
 *
 * @return {Element} the element
 */
function assign(element, ...styleSources) {
  const target = element.style;

  forEach(styleSources, function(style) {
    if (!style) {
      return;
    }

    forEach(style, function(value, key) {
      target[key] = value;
    });
  });

  return element;
}

/**
 * Set attribute `name` to `val`, or get attr `name`.
 *
 * @param {Element} el
 * @param {String} name
 * @param {String} [val]
 * @api public
 */
function attr(el, name, val) {

  // get
  if (arguments.length == 2) {
    return el.getAttribute(name);
  }

  // remove
  if (val === null) {
    return el.removeAttribute(name);
  }

  // set
  el.setAttribute(name, val);

  return el;
}

/**
 * Taken from https://github.com/component/classes
 *
 * Without the component bits.
 */

/**
 * toString reference.
 */

const toString = Object.prototype.toString;

/**
 * Wrap `el` in a `ClassList`.
 *
 * @param {Element} el
 * @return {ClassList}
 * @api public
 */

function classes(el) {
  return new ClassList(el);
}

/**
 * Initialize a new ClassList for `el`.
 *
 * @param {Element} el
 * @api private
 */

function ClassList(el) {
  if (!el || !el.nodeType) {
    throw new Error('A DOM element reference is required');
  }
  this.el = el;
  this.list = el.classList;
}

/**
 * Add class `name` if not already present.
 *
 * @param {String} name
 * @return {ClassList}
 * @api public
 */

ClassList.prototype.add = function(name) {
  this.list.add(name);
  return this;
};

/**
 * Remove class `name` when present, or
 * pass a regular expression to remove
 * any which match.
 *
 * @param {String|RegExp} name
 * @return {ClassList}
 * @api public
 */

ClassList.prototype.remove = function(name) {
  if ('[object RegExp]' == toString.call(name)) {
    return this.removeMatching(name);
  }

  this.list.remove(name);
  return this;
};

/**
 * Remove all classes matching `re`.
 *
 * @param {RegExp} re
 * @return {ClassList}
 * @api private
 */

ClassList.prototype.removeMatching = function(re) {
  const arr = this.array();
  for (let i = 0; i < arr.length; i++) {
    if (re.test(arr[i])) {
      this.remove(arr[i]);
    }
  }
  return this;
};

/**
 * Toggle class `name`, can force state via `force`.
 *
 * For browsers that support classList, but do not support `force` yet,
 * the mistake will be detected and corrected.
 *
 * @param {String} name
 * @param {Boolean} force
 * @return {ClassList}
 * @api public
 */

ClassList.prototype.toggle = function(name, force) {
  if ('undefined' !== typeof force) {
    if (force !== this.list.toggle(name, force)) {
      this.list.toggle(name); // toggle again to correct
    }
  } else {
    this.list.toggle(name);
  }
  return this;
};

/**
 * Return an array of classes.
 *
 * @return {Array}
 * @api public
 */

ClassList.prototype.array = function() {
  return Array.from(this.list);
};

/**
 * Check if class `name` is present.
 *
 * @param {String} name
 * @return {ClassList}
 * @api public
 */

ClassList.prototype.has =
ClassList.prototype.contains = function(name) {
  return this.list.contains(name);
};

/**
 * Clear utility
 */

/**
 * Removes all children from the given element
 *
 * @param {Element} element
 *
 * @return {Element} the element (for chaining)
 */
function clear(element) {
  var child;

  while ((child = element.firstChild)) {
    element.removeChild(child);
  }

  return element;
}

/**
 * Closest
 *
 * @param {Element} el
 * @param {string} selector
 * @param {boolean} checkYourSelf (optional)
 */
function closest(element, selector, checkYourSelf) {
  var actualElement = checkYourSelf ? element : element.parentNode;

  return actualElement && typeof actualElement.closest === 'function' && actualElement.closest(selector) || null;
}

function getDefaultExportFromCjs (x) {
	return x && x.__esModule && Object.prototype.hasOwnProperty.call(x, 'default') ? x['default'] : x;
}

var componentEvent = {};

var hasRequiredComponentEvent;

function requireComponentEvent () {
	if (hasRequiredComponentEvent) return componentEvent;
	hasRequiredComponentEvent = 1;
	var bind, unbind, prefix;

	function detect () {
	  bind = window.addEventListener ? 'addEventListener' : 'attachEvent';
	  unbind = window.removeEventListener ? 'removeEventListener' : 'detachEvent';
	  prefix = bind !== 'addEventListener' ? 'on' : '';
	}

	/**
	 * Bind `el` event `type` to `fn`.
	 *
	 * @param {Element} el
	 * @param {String} type
	 * @param {Function} fn
	 * @param {Boolean} capture
	 * @return {Function}
	 * @api public
	 */

	componentEvent.bind = function(el, type, fn, capture){
	  if (!bind) detect();
	  el[bind](prefix + type, fn, capture || false);
	  return fn;
	};

	/**
	 * Unbind `el` event `type`'s callback `fn`.
	 *
	 * @param {Element} el
	 * @param {String} type
	 * @param {Function} fn
	 * @param {Boolean} capture
	 * @return {Function}
	 * @api public
	 */

	componentEvent.unbind = function(el, type, fn, capture){
	  if (!unbind) detect();
	  el[unbind](prefix + type, fn, capture || false);
	  return fn;
	};
	return componentEvent;
}

var componentEventExports = requireComponentEvent();
var index = /*@__PURE__*/getDefaultExportFromCjs(componentEventExports);

var event = /*#__PURE__*/_mergeNamespaces({
  __proto__: null,
  default: index
}, [componentEventExports]);

/**
 * Module dependencies.
 */


/**
 * Delegate event `type` to `selector`
 * and invoke `fn(e)`. A callback function
 * is returned which may be passed to `.unbind()`.
 *
 * @param {Element} el
 * @param {String} selector
 * @param {String} type
 * @param {Function} fn
 * @param {Boolean} capture
 * @return {Function}
 * @api public
 */

// Some events don't bubble, so we want to bind to the capture phase instead
// when delegating.
var forceCaptureEvents = [ 'focus', 'blur' ];

function bind(el, selector, type, fn, capture) {
  if (forceCaptureEvents.indexOf(type) !== -1) {
    capture = true;
  }

  return event.bind(el, type, function(e) {
    var target = e.target || e.srcElement;
    e.delegateTarget = closest(target, selector, true);
    if (e.delegateTarget) {
      fn.call(el, e);
    }
  }, capture);
}

/**
 * Unbind event `type`'s callback `fn`.
 *
 * @param {Element} el
 * @param {String} type
 * @param {Function} fn
 * @param {Boolean} capture
 * @api public
 */
function unbind(el, type, fn, capture) {
  if (forceCaptureEvents.indexOf(type) !== -1) {
    capture = true;
  }

  return event.unbind(el, type, fn, capture);
}

var delegate = {
  bind,
  unbind
};

/**
 * @param { HTMLElement } element
 * @param { String } selector
 *
 * @return { boolean }
 */
function matches(element, selector) {
  return element && typeof element.matches === 'function' && element.matches(selector) || false;
}

function query(selector, el) {
  el = el || document;

  return el.querySelector(selector);
}

function all(selector, el) {
  el = el || document;

  return el.querySelectorAll(selector);
}

function remove(el) {
  el.parentNode && el.parentNode.removeChild(el);
}

export { assign as assignStyle, attr, classes, clear, closest, delegate, event, matches, query, all as queryAll, remove };
//# sourceMappingURL=index.js.map

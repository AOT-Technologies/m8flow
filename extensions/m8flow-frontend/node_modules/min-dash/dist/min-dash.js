(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
  typeof define === 'function' && define.amd ? define(['exports'], factory) :
  (global = typeof globalThis !== 'undefined' ? globalThis : global || self, factory(global.MinDash = {}));
})(this, (function (exports) { 'use strict';

  /**
   * Flatten array, one level deep.
   *
   * @template T
   *
   * @param {T[][] | T[] | null} [arr]
   *
   * @return {T[]}
   */
  function flatten(arr) {
    return Array.prototype.concat.apply([], arr);
  }

  const nativeToString = Object.prototype.toString;
  const nativeHasOwnProperty = Object.prototype.hasOwnProperty;

  function isUndefined(obj) {
    return obj === undefined;
  }

  function isDefined(obj) {
    return obj !== undefined;
  }

  function isNil(obj) {
    return obj == null;
  }

  function isArray(obj) {
    return nativeToString.call(obj) === '[object Array]';
  }

  function isObject(obj) {
    return nativeToString.call(obj) === '[object Object]';
  }

  function isNumber(obj) {
    return nativeToString.call(obj) === '[object Number]';
  }

  /**
   * @param {any} obj
   *
   * @return {boolean}
   */
  function isFunction(obj) {
    const tag = nativeToString.call(obj);

    return (
      tag === '[object Function]' ||
      tag === '[object AsyncFunction]' ||
      tag === '[object GeneratorFunction]' ||
      tag === '[object AsyncGeneratorFunction]' ||
      tag === '[object Proxy]'
    );
  }

  function isString(obj) {
    return nativeToString.call(obj) === '[object String]';
  }


  /**
   * Ensure collection is an array.
   *
   * @param {Object} obj
   */
  function ensureArray(obj) {

    if (isArray(obj)) {
      return;
    }

    throw new Error('must supply array');
  }

  /**
   * Return true, if target owns a property with the given key.
   *
   * @param {Object} target
   * @param {String} key
   *
   * @return {Boolean}
   */
  function has(target, key) {
    return !isNil(target) && nativeHasOwnProperty.call(target, key);
  }

  /**
   * @template T
   * @typedef { (
   *   ((e: T) => boolean) |
   *   ((e: T, idx: number) => boolean) |
   *   ((e: T, key: string) => boolean) |
   *   string |
   *   number
   * ) } Matcher
   */

  /**
   * @template T
   * @template U
   *
   * @typedef { (
   *   ((e: T) => U) | string | number
   * ) } Extractor
   */


  /**
   * @template T
   * @typedef { (val: T, key: any) => boolean } MatchFn
   */

  /**
   * @template T
   * @typedef { T[] } ArrayCollection
   */

  /**
   * @template T
   * @typedef { { [key: string]: T } } StringKeyValueCollection
   */

  /**
   * @template T
   * @typedef { { [key: number]: T } } NumberKeyValueCollection
   */

  /**
   * @template T
   * @typedef { StringKeyValueCollection<T> | NumberKeyValueCollection<T> } KeyValueCollection
   */

  /**
   * @template T
   * @typedef { KeyValueCollection<T> | ArrayCollection<T> } Collection
   */

  /**
   * Find element in collection.
   *
   * @template T
   * @param {Collection<T>} collection
   * @param {Matcher<T>} matcher
   *
   * @return {Object}
   */
  function find(collection, matcher) {

    const matchFn = toMatcher(matcher);

    let match;

    forEach(collection, function(val, key) {
      if (matchFn(val, key)) {
        match = val;

        return false;
      }
    });

    return match;

  }


  /**
   * Find element index in collection.
   *
   * @template T
   * @param {Collection<T>} collection
   * @param {Matcher<T>} matcher
   *
   * @return {number | string | undefined}
   */
  function findIndex(collection, matcher) {

    const matchFn = toMatcher(matcher);

    let idx = isArray(collection) ? -1 : undefined;

    forEach(collection, function(val, key) {
      if (matchFn(val, key)) {
        idx = key;

        return false;
      }
    });

    return idx;
  }


  /**
   * Filter elements in collection.
   *
   * @template T
   * @param {Collection<T>} collection
   * @param {Matcher<T>} matcher
   *
   * @return {T[]} result
   */
  function filter(collection, matcher) {

    const matchFn = toMatcher(matcher);

    let result = [];

    forEach(collection, function(val, key) {
      if (matchFn(val, key)) {
        result.push(val);
      }
    });

    return result;
  }


  /**
   * Iterate over collection; returning something
   * (non-undefined) will stop iteration.
   *
   * @template T
   * @param {Collection<T>} collection
   * @param { ((item: T, idx: number) => (boolean|void)) | ((item: T, key: string) => (boolean|void)) } iterator
   *
   * @return {T} return result that stopped the iteration
   */
  function forEach(collection, iterator) {

    let val,
        result;

    if (isUndefined(collection)) {
      return;
    }

    const convertKey = isArray(collection) ? toNum : identity;

    for (let key in collection) {

      if (has(collection, key)) {
        val = collection[key];

        result = iterator(val, convertKey(key));

        if (result === false) {
          return val;
        }
      }
    }
  }

  /**
   * Return collection without element.
   *
   * @template T
   * @param {ArrayCollection<T>} arr
   * @param {Matcher<T>} matcher
   *
   * @return {T[]}
   */
  function without(arr, matcher) {

    if (isUndefined(arr)) {
      return [];
    }

    ensureArray(arr);

    const matchFn = toMatcher(matcher);

    return arr.filter(function(el, idx) {
      return !matchFn(el, idx);
    });

  }


  /**
   * Reduce collection, returning a single result.
   *
   * @template T
   * @template V
   *
   * @param {Collection<T>} collection
   * @param {(result: V, entry: T, index: any) => V} iterator
   * @param {V} result
   *
   * @return {V} result returned from last iterator
   */
  function reduce(collection, iterator, result) {

    forEach(collection, function(value, idx) {
      result = iterator(result, value, idx);
    });

    return result;
  }


  /**
   * Return true if every element in the collection
   * matches the criteria.
   *
   * @param  {Object|Array} collection
   * @param  {Function} matcher
   *
   * @return {Boolean}
   */
  function every(collection, matcher) {

    return !!reduce(collection, function(matches, val, key) {
      return matches && matcher(val, key);
    }, true);
  }


  /**
   * Return true if some elements in the collection
   * match the criteria.
   *
   * @param  {Object|Array} collection
   * @param  {Function} matcher
   *
   * @return {Boolean}
   */
  function some(collection, matcher) {

    return !!find(collection, matcher);
  }


  /**
   * Transform a collection into another collection
   * by piping each member through the given fn.
   *
   * @param  {Object|Array}   collection
   * @param  {Function} fn
   *
   * @return {Array} transformed collection
   */
  function map(collection, fn) {

    let result = [];

    forEach(collection, function(val, key) {
      result.push(fn(val, key));
    });

    return result;
  }


  /**
   * Get the collections keys.
   *
   * @param  {Object|Array} collection
   *
   * @return {Array}
   */
  function keys(collection) {
    return collection && Object.keys(collection) || [];
  }


  /**
   * Shorthand for `keys(o).length`.
   *
   * @param  {Object|Array} collection
   *
   * @return {Number}
   */
  function size(collection) {
    return keys(collection).length;
  }


  /**
   * Get the values in the collection.
   *
   * @param  {Object|Array} collection
   *
   * @return {Array}
   */
  function values(collection) {
    return map(collection, (val) => val);
  }


  /**
   * Group collection members by attribute.
   *
   * @param {Object|Array} collection
   * @param {Extractor} extractor
   *
   * @return {Object} map with { attrValue => [ a, b, c ] }
   */
  function groupBy(collection, extractor, grouped = {}) {

    extractor = toExtractor(extractor);

    forEach(collection, function(val) {
      let discriminator = extractor(val) || '_';

      let group = grouped[discriminator];

      if (!group) {
        group = grouped[discriminator] = [];
      }

      group.push(val);
    });

    return grouped;
  }


  function uniqueBy(extractor, ...collections) {

    extractor = toExtractor(extractor);

    let grouped = {};

    forEach(collections, (c) => groupBy(c, extractor, grouped));

    let result = map(grouped, function(val, key) {
      return val[0];
    });

    return result;
  }


  const unionBy = uniqueBy;



  /**
   * Sort collection by criteria.
   *
   * @template T
   *
   * @param {Collection<T>} collection
   * @param {Extractor<T, number | string>} extractor
   *
   * @return {Array}
   */
  function sortBy(collection, extractor) {

    extractor = toExtractor(extractor);

    let sorted = [];

    forEach(collection, function(value, key) {
      let disc = extractor(value, key);

      let entry = {
        d: disc,
        v: value
      };

      for (var idx = 0; idx < sorted.length; idx++) {
        let { d } = sorted[idx];

        if (disc < d) {
          sorted.splice(idx, 0, entry);
          return;
        }
      }

      // not inserted, append (!)
      sorted.push(entry);
    });

    return map(sorted, (e) => e.v);
  }


  /**
   * Create an object pattern matcher.
   *
   * @example
   *
   * ```javascript
   * const matcher = matchPattern({ id: 1 });
   *
   * let element = find(elements, matcher);
   * ```
   *
   * @template T
   *
   * @param {T} pattern
   *
   * @return { (el: any) =>  boolean } matcherFn
   */
  function matchPattern(pattern) {

    return function(el) {

      return every(pattern, function(val, key) {
        return el[key] === val;
      });

    };
  }


  /**
   * @param {string | ((e: any) => any) } extractor
   *
   * @return { (e: any) => any }
   */
  function toExtractor(extractor) {

    /**
     * @satisfies { (e: any) => any }
     */
    return isFunction(extractor) ? extractor : (e) => {

      // @ts-ignore: just works
      return e[extractor];
    };
  }


  /**
   * @template T
   * @param {Matcher<T>} matcher
   *
   * @return {MatchFn<T>}
   */
  function toMatcher(matcher) {
    return isFunction(matcher) ? matcher : (e) => {
      return e === matcher;
    };
  }


  function identity(arg) {
    return arg;
  }

  function toNum(arg) {
    return Number(arg);
  }

  /* global setTimeout clearTimeout */

  /**
   * @typedef { {
   *   (...args: any[]): any;
   *   flush: () => void;
   *   cancel: () => void;
   * } } DebouncedFunction
   */

  /**
   * Debounce fn, calling it only once if the given time
   * elapsed between calls.
   *
   * Lodash-style the function exposes methods to `#clear`
   * and `#flush` to control internal behavior.
   *
   * @param  {Function} fn
   * @param  {Number} timeout
   *
   * @return {DebouncedFunction} debounced function
   */
  function debounce(fn, timeout) {

    let timer;

    let lastArgs;
    let lastThis;

    let lastNow;

    function fire(force) {

      let now = Date.now();

      let scheduledDiff = force ? 0 : (lastNow + timeout) - now;

      if (scheduledDiff > 0) {
        return schedule(scheduledDiff);
      }

      fn.apply(lastThis, lastArgs);

      clear();
    }

    function schedule(timeout) {
      timer = setTimeout(fire, timeout);
    }

    function clear() {
      if (timer) {
        clearTimeout(timer);
      }

      timer = lastNow = lastArgs = lastThis = undefined;
    }

    function flush() {
      if (timer) {
        fire(true);
      }

      clear();
    }

    /**
     * @type { DebouncedFunction }
     */
    function callback(...args) {
      lastNow = Date.now();

      lastArgs = args;
      lastThis = this;

      // ensure an execution is scheduled
      if (!timer) {
        schedule(timeout);
      }
    }

    callback.flush = flush;
    callback.cancel = clear;

    return callback;
  }

  /**
   * Throttle fn, calling at most once
   * in the given interval.
   *
   * @param  {Function} fn
   * @param  {Number} interval
   *
   * @return {Function} throttled function
   */
  function throttle(fn, interval) {
    let throttling = false;

    return function(...args) {

      if (throttling) {
        return;
      }

      fn(...args);
      throttling = true;

      setTimeout(() => {
        throttling = false;
      }, interval);
    };
  }

  /**
   * Bind function against target <this>.
   *
   * @param  {Function} fn
   * @param  {Object}   target
   *
   * @return {Function} bound function
   */
  function bind(fn, target) {
    return fn.bind(target);
  }

  /**
   * Convenience wrapper for `Object.assign`.
   *
   * @param {Object} target
   * @param {...Object} others
   *
   * @return {Object} the target
   */
  function assign(target, ...others) {
    return Object.assign(target, ...others);
  }

  /**
   * Sets a nested property of a given object to the specified value.
   *
   * This mutates the object and returns it.
   *
   * @template T
   *
   * @param {T} target The target of the set operation.
   * @param {(string|number)[]} path The path to the nested value.
   * @param {any} value The value to set.
   *
   * @return {T}
   */
  function set(target, path, value) {

    let currentTarget = target;

    forEach(path, function(key, idx) {

      if (typeof key !== 'number' && typeof key !== 'string') {
        throw new Error('illegal key type: ' + typeof key + '. Key should be of type number or string.');
      }

      if (key === 'constructor') {
        throw new Error('illegal key: constructor');
      }

      if (key === '__proto__') {
        throw new Error('illegal key: __proto__');
      }

      let nextKey = path[idx + 1];
      let nextTarget = currentTarget[key];

      if (isDefined(nextKey) && isNil(nextTarget)) {
        nextTarget = currentTarget[key] = isNaN(+nextKey) ? {} : [];
      }

      if (isUndefined(nextKey)) {
        if (isUndefined(value)) {
          delete currentTarget[key];
        } else {
          currentTarget[key] = value;
        }
      } else {
        currentTarget = nextTarget;
      }
    });

    return target;
  }


  /**
   * Gets a nested property of a given object.
   *
   * @param {Object} target The target of the get operation.
   * @param {(string|number)[]} path The path to the nested value.
   * @param {any} [defaultValue] The value to return if no value exists.
   *
   * @return {any}
   */
  function get(target, path, defaultValue) {

    let currentTarget = target;

    forEach(path, function(key) {

      // accessing nil property yields <undefined>
      if (isNil(currentTarget)) {
        currentTarget = undefined;

        return false;
      }

      currentTarget = currentTarget[key];
    });

    return isUndefined(currentTarget) ? defaultValue : currentTarget;
  }

  /**
   * Pick properties from the given target.
   *
   * @template T
   * @template {any[]} V
   *
   * @param {T} target
   * @param {V} properties
   *
   * @return Pick<T, V>
   */
  function pick(target, properties) {

    let result = {};

    let obj = Object(target);

    forEach(properties, function(prop) {

      if (prop in obj) {
        result[prop] = target[prop];
      }
    });

    return result;
  }

  /**
   * Pick all target properties, excluding the given ones.
   *
   * @template T
   * @template {any[]} V
   *
   * @param {T} target
   * @param {V} properties
   *
   * @return {Omit<T, V>} target
   */
  function omit(target, properties) {

    let result = {};

    let obj = Object(target);

    forEach(obj, function(prop, key) {

      if (properties.indexOf(key) === -1) {
        result[key] = prop;
      }
    });

    return result;
  }

  /**
   * Recursively merge `...sources` into given target.
   *
   * Does support merging objects; does not support merging arrays.
   *
   * @param {Object} target
   * @param {...Object} sources
   *
   * @return {Object} the target
   */
  function merge(target, ...sources) {

    if (!sources.length) {
      return target;
    }

    forEach(sources, function(source) {

      // skip non-obj sources, i.e. null
      if (!source || !isObject(source)) {
        return;
      }

      forEach(source, function(sourceVal, key) {

        if (key === '__proto__') {
          return;
        }

        let targetVal = target[key];

        if (isObject(sourceVal)) {

          if (!isObject(targetVal)) {

            // override target[key] with object
            targetVal = {};
          }

          target[key] = merge(targetVal, sourceVal);
        } else {
          target[key] = sourceVal;
        }

      });
    });

    return target;
  }

  exports.assign = assign;
  exports.bind = bind;
  exports.debounce = debounce;
  exports.ensureArray = ensureArray;
  exports.every = every;
  exports.filter = filter;
  exports.find = find;
  exports.findIndex = findIndex;
  exports.flatten = flatten;
  exports.forEach = forEach;
  exports.get = get;
  exports.groupBy = groupBy;
  exports.has = has;
  exports.isArray = isArray;
  exports.isDefined = isDefined;
  exports.isFunction = isFunction;
  exports.isNil = isNil;
  exports.isNumber = isNumber;
  exports.isObject = isObject;
  exports.isString = isString;
  exports.isUndefined = isUndefined;
  exports.keys = keys;
  exports.map = map;
  exports.matchPattern = matchPattern;
  exports.merge = merge;
  exports.omit = omit;
  exports.pick = pick;
  exports.reduce = reduce;
  exports.set = set;
  exports.size = size;
  exports.some = some;
  exports.sortBy = sortBy;
  exports.throttle = throttle;
  exports.unionBy = unionBy;
  exports.uniqueBy = uniqueBy;
  exports.values = values;
  exports.without = without;

}));

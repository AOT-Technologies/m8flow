/**
 * Extends a collection with {@link Refs} aware methods
 *
 * @param {Array<Object>} collection
 * @param {Refs} refs instance
 * @param {Object} property represented by the collection
 * @param {Object} target object the collection is attached to
 *
 * @return {RefsCollection<Object>} the extended array
 */
function extend(collection, refs, property, target) {
  var inverseProperty = property.inverse;

  /**
   * Removes the given element from the array and returns it.
   *
   * @method RefsCollection#remove
   *
   * @param {Object} element the element to remove
   */
  Object.defineProperty(collection, 'remove', {
    value: function (element) {
      var idx = this.indexOf(element);
      if (idx !== -1) {
        this.splice(idx, 1);

        // unset inverse
        refs.unset(element, inverseProperty, target);
      }
      return element;
    }
  });

  /**
   * Returns true if the collection contains the given element
   *
   * @method RefsCollection#contains
   *
   * @param {Object} element the element to check for
   */
  Object.defineProperty(collection, 'contains', {
    value: function (element) {
      return this.indexOf(element) !== -1;
    }
  });

  /**
   * Adds an element to the array, unless it exists already (set semantics).
   *
   * @method RefsCollection#add
   *
   * @param {Object} element the element to add
   * @param {Number} optional index to add element to
   *                 (possibly moving other elements around)
   */
  Object.defineProperty(collection, 'add', {
    value: function (element, idx) {
      var currentIdx = this.indexOf(element);
      if (typeof idx === 'undefined') {
        if (currentIdx !== -1) {
          // element already in collection (!)
          return;
        }

        // add to end of array, as no idx is specified
        idx = this.length;
      }

      // handle already in collection
      if (currentIdx !== -1) {
        // remove element from currentIdx
        this.splice(currentIdx, 1);
      }

      // add element at idx
      this.splice(idx, 0, element);
      if (currentIdx === -1) {
        // set inverse, unless element was
        // in collection already
        refs.set(element, inverseProperty, target);
      }
    }
  });

  // a simple marker, identifying this element
  // as being a refs collection
  Object.defineProperty(collection, '__refs_collection', {
    value: true
  });
  return collection;
}

/**
 * Checks if a given collection is extended
 *
 * @param {Array<Object>} collection
 *
 * @return {boolean}
 */
function isExtended(collection) {
  return collection.__refs_collection === true;
}

var collection = {
  __proto__: null,
  extend: extend,
  isExtended: isExtended
};

function hasOwnProperty(e, property) {
  return Object.prototype.hasOwnProperty.call(e, property.name || property);
}
function defineCollectionProperty(ref, property, target) {
  var collection = extend(target[property.name] || [], ref, property, target);
  Object.defineProperty(target, property.name, {
    enumerable: property.enumerable,
    value: collection
  });
  if (collection.length) {
    collection.forEach(function (o) {
      ref.set(o, property.inverse, target);
    });
  }
}
function defineProperty(ref, property, target) {
  var inverseProperty = property.inverse;
  var _value = target[property.name];
  Object.defineProperty(target, property.name, {
    configurable: property.configurable,
    enumerable: property.enumerable,
    get: function () {
      return _value;
    },
    set: function (value) {
      // return if we already performed all changes
      if (value === _value) {
        return;
      }
      var old = _value;

      // temporary set null
      _value = null;
      if (old) {
        ref.unset(old, inverseProperty, target);
      }

      // set new value
      _value = value;

      // set inverse value
      ref.set(_value, inverseProperty, target);
    }
  });
}

/**
 * Creates a new references object defining two inversly related
 * attribute descriptors a and b.
 *
 * <p>
 *   When bound to an object using {@link Refs#bind} the references
 *   get activated and ensure that add and remove operations are applied
 *   reversely, too.
 * </p>
 *
 * <p>
 *   For attributes represented as collections {@link Refs} provides the
 *   {@link RefsCollection#add}, {@link RefsCollection#remove} and {@link RefsCollection#contains} extensions
 *   that must be used to properly hook into the inverse change mechanism.
 * </p>
 *
 * @class Refs
 *
 * @classdesc A bi-directional reference between two attributes.
 *
 * @param {Refs.AttributeDescriptor} a property descriptor
 * @param {Refs.AttributeDescriptor} b property descriptor
 *
 * @example
 *
 * var refs = Refs({ name: 'wheels', collection: true, enumerable: true }, { name: 'car' });
 *
 * var car = { name: 'toyota' };
 * var wheels = [{ pos: 'front-left' }, { pos: 'front-right' }];
 *
 * refs.bind(car, 'wheels');
 *
 * car.wheels // []
 * car.wheels.add(wheels[0]);
 * car.wheels.add(wheels[1]);
 *
 * car.wheels // [{ pos: 'front-left' }, { pos: 'front-right' }]
 *
 * wheels[0].car // { name: 'toyota' };
 * car.wheels.remove(wheels[0]);
 *
 * wheels[0].car // undefined
 */
function Refs(a, b) {
  if (!(this instanceof Refs)) {
    return new Refs(a, b);
  }

  // link
  a.inverse = b;
  b.inverse = a;
  this.props = {};
  this.props[a.name] = a;
  this.props[b.name] = b;
}

/**
 * Binds one side of a bi-directional reference to a
 * target object.
 *
 * @memberOf Refs
 *
 * @param  {Object} target
 * @param  {String} property
 */
Refs.prototype.bind = function (target, property) {
  if (typeof property === 'string') {
    if (!this.props[property]) {
      throw new Error('no property <' + property + '> in ref');
    }
    property = this.props[property];
  }
  if (property.collection) {
    defineCollectionProperty(this, property, target);
  } else {
    defineProperty(this, property, target);
  }
};
Refs.prototype.ensureRefsCollection = function (target, property) {
  var collection = target[property.name];
  if (!isExtended(collection)) {
    defineCollectionProperty(this, property, target);
  }
  return collection;
};
Refs.prototype.ensureBound = function (target, property) {
  if (!hasOwnProperty(target, property)) {
    this.bind(target, property);
  }
};
Refs.prototype.unset = function (target, property, value) {
  if (target) {
    this.ensureBound(target, property);
    if (property.collection) {
      this.ensureRefsCollection(target, property).remove(value);
    } else {
      target[property.name] = undefined;
    }
  }
};
Refs.prototype.set = function (target, property, value) {
  if (target) {
    this.ensureBound(target, property);
    if (property.collection) {
      this.ensureRefsCollection(target, property).add(value);
    } else {
      target[property.name] = value;
    }
  }
};

/**
 * An attribute descriptor to be used specify an attribute in a {@link Refs} instance
 *
 * @typedef {Object} Refs.AttributeDescriptor
 * @property {String} name
 * @property {boolean} [collection=false]
 * @property {boolean} [enumerable=false]
 */

exports.Collection = collection;
exports.Refs = Refs;

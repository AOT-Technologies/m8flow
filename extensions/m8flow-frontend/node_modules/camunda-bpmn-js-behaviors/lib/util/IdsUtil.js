import Ids from 'ids';

const ids = new Ids([ 32, 32, 1 ]);

/**
 * Get ID with prefix.
 */
export function getPrefixedId(prefix) {
  return ids.nextPrefixed(prefix);
}

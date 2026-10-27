/**
 * URL checks for expect(page).toHaveURL(...). They compare plain strings, so
 * no RegExp is built from variables (ids, file names).
 */
const decodedPath = (url: URL) => decodeURIComponent(url.pathname);

/** The URL path contains `part`. */
export const urlPathHas = (part: string) => (url: URL) => decodedPath(url).includes(part);

/** The URL path ends with `suffix`. */
export const urlPathEndsWith = (suffix: string) => (url: URL) => decodedPath(url).endsWith(suffix);

/** The ?group= query value is exactly `groupId`. */
export const urlGroupIs = (groupId: string) => (url: URL) => url.searchParams.get('group') === groupId;

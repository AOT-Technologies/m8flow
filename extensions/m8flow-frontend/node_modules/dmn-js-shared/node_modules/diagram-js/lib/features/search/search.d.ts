/**
 * Search items by query.
 *
 *
 * @param items elements to search in
 * @param pattern pattern to search for
 * @param options
 *
 * @returns
 */
export default function search<T extends SearchItem>(
  items: T[],
  pattern: string,
  options: {
      keys: string[];
  }
): SearchResult<T>[];
export type Token = {
    index: number;
    match: boolean;
    value: string;
};
export type Tokens = Token[];
export type SearchResult<R> = {
    item: R;
    tokens: Record<string, Tokens>;
};
export type SearchItem = Record<string, string | string[]>;

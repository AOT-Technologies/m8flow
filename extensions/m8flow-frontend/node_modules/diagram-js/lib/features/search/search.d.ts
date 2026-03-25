/**
 * Search items by query.
 *
 * @param items
 * @param pattern
 * @param options
 *
 * @returns
 */
export default function search(
  items: any[],
  pattern: string,
  options: {
      keys: string[];
  }
): SearchResults;
/**
* @param token
*
* @return
*/
export function isMatch(token: Token): boolean;
/**
* @param tokens
*
* @return
*/
export function hasMatch(tokens: Token[]): boolean;
/**
* Compares two token arrays.
*
* @param tokensA
* @param tokensB
*
* @returns
*/
export function compareTokens(tokensA: Token[], tokensB: Token[]): number;
/**
* Compares two strings.
*
* @param a
* @param b
*
* @returns
*/
export function compareStrings(a: string, b: string): number;
/**
* @param string
* @param pattern
*
* @return
*/
export function getMatchingTokens(string: string, pattern: string): Token[];
export type Token = {
    index: number;
    match: boolean;
    value: string;
};
export type Tokens = Token[];
export type SearchResult = {
    item: any;
    tokens: Record<string, Token[]>;
};
export type SearchResults = SearchResult[];

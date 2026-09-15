import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';

/** Main-thread tokenizer id. Monaco's built-in `json` language spawns a
 * worker that calls AMD `require.toUrl` — undefined under Vite, which
 * crashes the editor with `Cannot read properties of undefined (reading
 * 'toUrl')`. Format/validation stay in codeFormat/codeLint. */
export const M8FLOW_JSON_LANGUAGE = 'm8flow-json';

export function registerM8flowJsonLanguage(): void {
  const languages = monaco.languages;
  if (!languages?.register || !languages.setMonarchTokensProvider) return;
  if (languages.getLanguages?.().some((language) => language.id === M8FLOW_JSON_LANGUAGE)) return;
  languages.register({ id: M8FLOW_JSON_LANGUAGE });
  languages.setMonarchTokensProvider(M8FLOW_JSON_LANGUAGE, {
    tokenizer: {
      root: [
        [/[{}]/, 'delimiter.bracket'],
        [/[[\]]/, 'delimiter.square'],
        [/[;,]/, 'delimiter'],
        [/:/, 'delimiter'],
        [/"([^"\\]|\\.)*"(?=\s*:)/, 'type.identifier'],
        [/"([^"\\]|\\.)*"/, 'string'],
        [/\b(?:true|false|null)\b/, 'keyword'],
        [/-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/, 'number'],
      ],
    },
  });
}

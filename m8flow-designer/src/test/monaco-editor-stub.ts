// Test stub for `monaco-editor`. The real package resolves only in a browser
// (canvas/workers) and can't be loaded in the jsdom/node test environment, so
// vite.config's `test.alias` points `monaco-editor` here. EditorDialog only
// touches `MarkerSeverity` and `editor.setModelMarkers`.
export const MarkerSeverity = { Error: 8, Warning: 4 } as const;

export const editor = {
  setModelMarkers: () => {},
};

export const languages = {
  getLanguages: () => [] as Array<{ id: string }>,
  register: () => {},
  setMonarchTokensProvider: () => {},
};

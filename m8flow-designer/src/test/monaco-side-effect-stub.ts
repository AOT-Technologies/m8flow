// Test stub for monaco-editor's side-effect-only submodule imports
// (`editor.all`, and the per-language `*.contribution` modules). These only
// register features/languages against the real Monaco runtime as a module
// load side effect — nothing they export is ever used directly, and (like
// the base `monaco-editor` package, see monaco-editor-stub.ts) the real
// files only resolve/run in a browser, not jsdom/node. An empty module is a
// correct stand-in for all of them in tests.
export {};

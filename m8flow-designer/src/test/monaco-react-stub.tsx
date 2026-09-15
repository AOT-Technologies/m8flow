// Test stub for `@monaco-editor/react`. vite.config's `test.alias` points the
// package here so tests render a plain, controlled <textarea> instead of the
// real Monaco editor (which needs a browser). Mirrors the props EditorDialog
// uses: `value`, `onChange`. `onMount` is intentionally never called, so the
// component's editor/monaco refs stay null and the marker path no-ops.
type EditorProps = {
  value?: string;
  onChange?: (value: string | undefined) => void;
  options?: { ariaLabel?: string };
};

export const loader = { config: () => {} };

export default function Editor({ value, onChange, options }: EditorProps) {
  return (
    <textarea
      aria-label={options?.ariaLabel ?? 'code editor'}
      value={value ?? ''}
      onChange={(event) => onChange?.(event.target.value)}
    />
  );
}

/**
 * m8flow override: the "Import Process Model" button is intentionally hidden.
 *
 * Upstream renders this button in ProcessModelNew. m8flow does not expose model
 * import through the UI, so this override renders nothing.
 *
 * The props signature is kept so upstream's call site
 * (`<ProcessModelImportButton onClick={...} />`) still type-checks. The prop is
 * accepted and ignored.
 *
 * To restore the button, delete this file - the override resolver will fall
 * back to upstream's implementation automatically.
 */
interface ProcessModelImportButtonProps {
  onClick: () => void;
}

export function ProcessModelImportButton(
  _props: ProcessModelImportButtonProps,
) {
  return null;
}

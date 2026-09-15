/** Triggers a browser download of an in-memory Blob — shared by
 * `downloadTextFile` below and the Template modeler map's ticket 04
 * (template export, already a `Blob` from `exportTemplate()`, no text
 * wrapping needed). */
export function downloadBlob(fileName: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Triggers a browser download of in-memory text content — shared by the
 * modeler page's header Download button and the Processes overview's
 * per-file row Download icon. */
export function downloadTextFile(fileName: string, content: string, mimeType = 'application/xml') {
  downloadBlob(fileName, new Blob([content], { type: mimeType }));
}

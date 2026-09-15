/**
 * Process model identifiers use `/` on disk and in API `id` fields.
 * React Router path segments and the backend detail route use `:` instead.
 */
export function encodeProcessModelId(id: string): string {
  return id.split('/').join(':');
}

export function decodeProcessModelId(encoded: string): string {
  return encoded.split(':').join('/');
}

/**
 * URL-friendly process-model leaf from a display name. Matches backend
 * `catalog.slugify_process_model_leaf`: lowercase, whitespace to hyphens,
 * keep `[a-z0-9_-]`. Empty if nothing usable remains.
 */
export function slugifyProcessModelId(displayName: string): string {
  return displayName
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9_-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^[-_]+|[-_]+$/g, '');
}

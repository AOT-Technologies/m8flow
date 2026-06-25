/**
 * Derive a template_key from a display name: trim, lowercase, spaces to hyphens,
 * strip non-alphanumeric except hyphen/underscore, collapse repeated hyphens.
 * Returns empty string if result would be empty.
 */
export function nameToTemplateKey(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "";
  const slug = trimmed
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return slug;
}

/** Allowed characters in a template display name: letters, numbers, spaces, hyphen, underscore. */
export const TEMPLATE_NAME_PATTERN = /^[A-Za-z0-9 _-]+$/;

/** Maximum length of a template display name (trimmed). */
export const TEMPLATE_NAME_MAX_LENGTH = 100;

/** True if the trimmed name contains only allowed characters. */
export function isValidTemplateName(name: string): boolean {
  return TEMPLATE_NAME_PATTERN.test(name.trim());
}

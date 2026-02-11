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

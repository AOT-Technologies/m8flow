import type { Template, TemplateFile } from "../types/template";

/**
 * Sort an array of files so the primary file (identified by name) comes first.
 * Preserves relative order of all other files (stable sort).
 */
export function sortFilesWithPrimaryFirst<T extends { name: string }>(
  files: T[],
  primaryFileName: string
): T[] {
  if (!primaryFileName) return files;
  return [...files].sort((a, b) => {
    if (a.name === primaryFileName) return -1;
    if (b.name === primaryFileName) return 1;
    return 0;
  });
}

/**
 * Normalize a raw API response object into a typed Template.
 * Converts ISO date strings to epoch seconds for Spiff-style display.
 */
export function normalizeTemplate(raw: Record<string, unknown>): Template {
  const created = raw.createdAt as string | undefined;
  const updated = raw.updatedAt as string | undefined;
  const createdAtInSeconds = created
    ? Math.floor(new Date(created).getTime() / 1000)
    : 0;
  const updatedAtInSeconds = updated
    ? Math.floor(new Date(updated).getTime() / 1000)
    : 0;
  return {
    ...raw,
    files: (raw.files as TemplateFile[]) ?? [],
    createdAtInSeconds,
    updatedAtInSeconds,
  } as Template;
}

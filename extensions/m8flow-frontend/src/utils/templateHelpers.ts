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

function secondsFromApiOrIso(seconds: unknown, iso: unknown): number {
  if (typeof seconds === "number" && !Number.isNaN(seconds)) return seconds;
  if (typeof iso === "string") {
    const ms = Date.parse(iso);
    if (!Number.isNaN(ms)) return Math.floor(ms / 1000);
  }
  return 0;
}

/**
 * Normalize a raw API response object into a typed Template.
 * Uses createdAtInSeconds/updatedAtInSeconds from API when present, else derives from createdAt/updatedAt ISO strings.
 */
export function normalizeTemplate(raw: Record<string, unknown>): Template {
  const createdAtInSeconds = secondsFromApiOrIso(raw.createdAtInSeconds, raw.createdAt);
  const updatedAtInSeconds = secondsFromApiOrIso(raw.updatedAtInSeconds, raw.updatedAt);
  return {
    ...raw,
    files: (raw.files as TemplateFile[]) ?? [],
    createdAtInSeconds,
    updatedAtInSeconds,
  } as Template;
}

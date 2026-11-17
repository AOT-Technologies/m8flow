import type { Page } from '@playwright/test';

import { BACKEND_BASE_URL } from './fixtures';

/**
 * Reads, writes and deletes single files of a process model through the
 * same routes the modeler uses (GET/PUT/DELETE
 * /process-models/{id}/files/{file_name}). PUT also adds a file that does
 * not exist yet.
 *
 * Used by the seed (helpers/seedCatalog.ts) to keep the seeded models equal
 * to the files in e2e/seed/catalog/, and by tests that add a file to their
 * own copy of a seeded model. Never call it on a seeded model from a test.
 *
 * Uses `page.request` (not a fresh APIRequestContext) so it fires from the
 * page's own already-authenticated session -- call it after signing in.
 */
export async function seedProcessModelFile(
  page: Page,
  fileName: string,
  xmlContent: string,
  modelRouteId: string,
): Promise<void> {
  const accessToken = await readAccessTokenCookie(page);
  const url = fileUrl(modelRouteId, fileName);

  const response = await page.request.put(url, {
    data: xmlContent,
    headers: {
      'Content-Type': 'application/octet-stream',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });

  if (!response.ok()) {
    throw new Error(
      `seedProcessModelFile: PUT ${fileName} failed with ${response.status()} — ${await response.text()}`,
    );
  }
}

/** DELETE a seeded process-model file. 404 is success (already gone). */
export async function deleteProcessModelFile(
  page: Page,
  fileName: string,
  modelRouteId: string,
): Promise<void> {
  const accessToken = await readAccessTokenCookie(page);
  const url = fileUrl(modelRouteId, fileName);

  const response = await page.request.delete(url, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });

  if (!response.ok() && response.status() !== 404) {
    throw new Error(
      `deleteProcessModelFile: DELETE ${fileName} failed with ${response.status()} — ${await response.text()}`,
    );
  }
}

/** Content of a process-model file, or undefined when it does not exist. */
export async function readProcessModelFile(
  page: Page,
  fileName: string,
  modelRouteId: string,
): Promise<string | undefined> {
  const accessToken = await readAccessTokenCookie(page);
  const response = await page.request.get(fileUrl(modelRouteId, fileName), {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (response.status() === 404) return undefined;
  if (!response.ok()) {
    throw new Error(`readProcessModelFile: GET ${fileName} failed with ${response.status()} — ${await response.text()}`);
  }
  return response.text();
}

function fileUrl(modelRouteId: string, fileName: string): string {
  const encodedId = modelRouteId.split(':').map(encodeURIComponent).join(':');
  return `${BACKEND_BASE_URL}/v1.0/m8flow/process-models/${encodedId}/files/${encodeURIComponent(fileName)}`;
}

/** Same cookie api.ts's apiGet/saveProcessModelFileContent read to build the Bearer header. */
async function readAccessTokenCookie(page: Page): Promise<string | null> {
  const cookies = await page.context().cookies();
  return cookies.find((cookie) => cookie.name === 'access_token')?.value ?? null;
}

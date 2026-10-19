import type { ParseKeys } from 'i18next';

import type { McpToolParameter } from '@/lib/mcpToolsApi';

export type ArgumentsResult =
  | { ok: true; args: Record<string, unknown> }
  | { ok: false; errors: Record<string, ParseKeys> };

// i18n keys, translated where the error is rendered (McpToolTryIt).
export const FIELD_REQUIRED: ParseKeys = 'mcpTools.tryIt.fieldRequired';
export const INVALID_NUMBER: ParseKeys = 'mcpTools.tryIt.invalidNumber';
export const INVALID_JSON: ParseKeys = 'mcpTools.tryIt.invalidJson';

/** Turn the Try it form's raw strings into the typed arguments the tool's schema expects.
 * Blank optional fields are omitted so the tool's own defaults apply; an unknown type
 * ("any") is sent as the string typed. */
export function buildArguments(parameters: McpToolParameter[], raw: Record<string, string>): ArgumentsResult {
  const args: Record<string, unknown> = {};
  const errors: Record<string, ParseKeys> = {};
  for (const param of parameters) {
    const text = (raw[param.name] ?? '').trim();
    if (!text) {
      if (param.required) errors[param.name] = FIELD_REQUIRED;
      continue;
    }
    if (param.type === 'integer' || param.type === 'number') {
      const value = Number(text);
      if (!Number.isFinite(value) || (param.type === 'integer' && !Number.isInteger(value))) {
        errors[param.name] = INVALID_NUMBER;
      } else {
        args[param.name] = value;
      }
    } else if (param.type === 'boolean') {
      args[param.name] = text === 'true';
    } else if (param.type === 'object' || param.type === 'array') {
      try {
        args[param.name] = JSON.parse(text);
      } catch {
        errors[param.name] = INVALID_JSON;
      }
    } else {
      args[param.name] = text;
    }
  }
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, args };
}

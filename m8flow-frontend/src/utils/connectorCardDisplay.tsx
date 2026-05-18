import { Avatar } from '@mui/material';

/** Prefix segment of operator `id` before `/` (matches connector proxy plugin display name). */
export function pluginKeyFromOperatorId(operatorId: string): string {
  const slash = operatorId.indexOf('/');
  if (slash === -1) {
    return operatorId;
  }
  return operatorId.slice(0, slash);
}

export function humanizeConnectorPluginKey(key: string): string {
  const withoutVersion = key.replace(/_v\d+$/i, '');
  const words = withoutVersion.split('_').filter(Boolean);
  return words
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

function readStringField(op: unknown, keys: string[]): string | undefined {
  if (!op || typeof op !== 'object') {
    return undefined;
  }
  const o = op as Record<string, unknown>;
  for (const k of keys) {
    const v = o[k];
    if (typeof v === 'string' && v.trim()) {
      return v.trim();
    }
  }
  return undefined;
}

/**
 * Card title: prefer explicit name fields from `/service-tasks` payloads when present,
 * otherwise derive from the plugin id prefix.
 */
export function displayNameForConnectorPlugin(
  pluginKey: string,
  operators: Array<{ id: string } & Record<string, unknown>>,
): string {
  for (const op of operators) {
    const fromApi = readStringField(op, [
      'name',
      'display_name',
      'displayName',
      'label',
      'title',
    ]);
    if (fromApi) {
      return fromApi;
    }
  }
  return humanizeConnectorPluginKey(pluginKey);
}

/** Two-letter (or shorter) initials from a human-readable connector name. */
export function initialsFromConnectorDisplayName(displayName: string): string {
  const trimmed = displayName.trim();
  if (!trimmed) {
    return '?';
  }
  const parts = trimmed.split(/\s+/).filter((p) => p.length > 0);
  if (parts.length >= 2) {
    const a = parts[0][0];
    const b = parts[1][0];
    if (a && b) {
      return `${a}${b}`.toUpperCase();
    }
  }
  const w = parts[0] ?? trimmed;
  const alnum = w.replace(/[^a-zA-Z0-9]/g, '');
  if (alnum.length >= 2) {
    return alnum.slice(0, 2).toUpperCase();
  }
  if (alnum.length === 1) {
    return alnum.toUpperCase();
  }
  return w.slice(0, Math.min(2, w.length)).toUpperCase();
}

function hueFromPluginKey(pluginKey: string): number {
  let h = 0;
  for (let i = 0; i < pluginKey.length; i += 1) {
    h = (Math.imul(31, h) + pluginKey.charCodeAt(i)) % 360;
  }
  return Math.abs(h);
}

/** Visual “icon”: initials from the (API or derived) display name, stable hue from plugin key. */
export function ConnectorNameAvatar({
  displayName,
  pluginKey,
}: {
  displayName: string;
  pluginKey: string;
}) {
  const initials = initialsFromConnectorDisplayName(displayName);
  const hue = hueFromPluginKey(pluginKey);

  return (
    <Avatar
      aria-label={displayName}
      variant="rounded"
      sx={{
        width: 40,
        height: 40,
        fontSize: '0.9rem',
        fontWeight: 700,
        flexShrink: 0,
        bgcolor: (theme) =>
          theme.palette.mode === 'dark'
            ? `hsl(${hue} 32% 34%)`
            : `hsl(${hue} 48% 44%)`,
        color: 'common.white',
      }}
    >
      {initials}
    </Avatar>
  );
}

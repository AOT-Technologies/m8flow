import type { ConnectorConfigField } from '../components/ConnectorOperationsModal';

/** Translator signature compatible with react-i18next's `t`. */
type Translate = (key: string, opts?: Record<string, unknown>) => string;

/** Simple, permissive email shape check (local@domain.tld). */
const EMAIL_RE = /^\S+@\S+\.\S+$/;

const isValidUrl = (value: string): boolean => {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
};

const isValidPort = (value: string): boolean => {
  if (!/^\d+$/.test(value)) {
    return false;
  }
  const port = Number(value);
  return port >= 1 && port <= 65535;
};

const isValidNumber = (value: string): boolean =>
  value !== '' && Number.isFinite(Number(value));

/**
 * Validate a single connector config field value, returning a ready-to-display
 * (translated) error message, or `undefined` when the value is acceptable.
 *
 * Validation runs against the trimmed value, in priority order:
 *   1. whitespace-only input (non-empty but trims to empty)
 *   2. required-but-empty (only when no secret already exists)
 *   3. min/max length
 *   4. format (url | email | port | number)
 *
 * An empty value for an optional (or already-configured) field is valid — it
 * means "leave the current secret unchanged".
 *
 * The translator is injected so callers keep error state as plain strings and
 * the util stays free of an i18n dependency for unit testing.
 */
export const validateConnectorField = (
  field: ConnectorConfigField,
  rawValue: string,
  isSet: boolean,
  t: Translate,
): string | undefined => {
  const value = rawValue.trim();

  // Non-empty input that is only whitespace.
  if (rawValue !== '' && value === '') {
    return t('connector_config_whitespace_only');
  }

  // Required field with nothing entered and no existing secret.
  if (value === '') {
    if (field.required && !isSet) {
      return t('connector_config_required_field');
    }
    return undefined; // optional/untouched -> leave unchanged
  }

  if (field.minLength !== undefined && value.length < field.minLength) {
    return t('connector_config_min_length', { min: field.minLength });
  }
  if (field.maxLength !== undefined && value.length > field.maxLength) {
    return t('connector_config_max_length', { max: field.maxLength });
  }

  switch (field.format) {
    case 'url':
      if (!isValidUrl(value)) {
        return t('connector_config_invalid_url');
      }
      break;
    case 'email':
      if (!EMAIL_RE.test(value)) {
        return t('connector_config_invalid_email');
      }
      break;
    case 'port':
      if (!isValidPort(value)) {
        return t('connector_config_invalid_port');
      }
      break;
    case 'number':
      if (!isValidNumber(value)) {
        return t('connector_config_invalid_number');
      }
      break;
    default:
      break;
  }

  return undefined;
};

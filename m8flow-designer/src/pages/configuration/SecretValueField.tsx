import { useTranslation } from 'react-i18next';

import { PasswordInput } from '@/components/ui/password-input';

/** Masked secret value input with a show/hide toggle. Leading/trailing
 * whitespace is warned about, not trimmed — some secrets legitimately carry it. */
export function SecretValueField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const hasEdgeWhitespace = value !== value.trim();
  return (
    <div className="mt-4">
      <label htmlFor={id} className="block text-sm font-medium text-foreground">
        {label}
      </label>
      <PasswordInput
        id={id}
        className="mt-1.5"
        toggleLabel={t('configuration.valueField.toggleLabel')}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="new-password"
        spellCheck={false}
        aria-describedby={hasEdgeWhitespace ? `${id}-help ${id}-whitespace` : `${id}-help`}
        data-testid="secret-value"
        required
      />
      <p id={`${id}-help`} className="mt-1.5 text-[13px] text-muted-foreground">
        {t('configuration.valueField.help')}
      </p>
      {/* Always mounted so the warning is announced when it appears mid-typing. */}
      <div aria-live="polite">
        {hasEdgeWhitespace ? (
          <p
            id={`${id}-whitespace`}
            className="mt-1 text-[13px] text-warning"
            data-testid="secret-value-whitespace"
          >
            {t('configuration.valueField.edgeWhitespace')}
          </p>
        ) : null}
      </div>
    </div>
  );
}

import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

/**
 * Hand-rolled, controlled JSON-Schema → EDITABLE form renderer for the Task
 * Review detail page. Unlike the (now removed) read-only renderer, this drives
 * an actual form the reviewer fills in — the task's own form, described by its
 * JSON schema. Deliberately NOT `@rjsf` or any form library: no new dependency,
 * stays native to shadcn/Tailwind primitives.
 *
 * Scope is the common JSON-Schema subset human-task forms use in practice:
 * - `string` + `enum` (or `oneOf` const/title) → native `<select>` styled like Input.
 * - `string` + `format: "date"` → `<input type="date">`.
 * - `string` plain → `<Input>`, or `<Textarea>` per the multiline heuristic below.
 * - `number`/`integer` → `<input type="number">` (parsed to number; empty → undefined).
 * - `boolean` → checkbox with the label.
 * - nested `object` (with `properties`) → titled sub-section that recurses (depth-capped).
 * Unknown/missing types degrade gracefully (skip or read-only) rather than crash.
 *
 * `readOnly` (schema-level) renders the value read-only instead of an input.
 */

export type JsonSchema = {
  type?: string;
  title?: string;
  format?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  enum?: unknown[];
  enumNames?: string[];
  oneOf?: Array<{ const?: unknown; title?: string }>;
  default?: unknown;
  minLength?: number;
  readOnly?: boolean;
};

/** A ui-schema node (RJSF-style). Always optional/nullable. */
export type UiSchema = Record<string, unknown> | null | undefined;

const MAX_DEPTH = 4;
const EM_DASH = '—';

/**
 * Keys/titles that read as prose get a multi-line <Textarea> instead of a
 * single-line <Input>, so fields like "reason" / "additional_notes" /
 * "comment" / "description" get room to write. A ui:widget/format of
 * "textarea" always wins over the heuristic.
 */
const TEXTAREA_KEY_RE = /reason|note|comment|description|message|detail/i;

function humanize(key: string): string {
  return key
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^\w/, (c) => c.toUpperCase());
}

function labelFor(key: string, field: JsonSchema): string {
  return field.title ?? humanize(key);
}

/** Ordered property keys, honouring a ui-schema `ui:order` when present. */
function orderedKeys(schema: JsonSchema, ui: UiSchema): string[] {
  const keys = Object.keys(schema.properties ?? {});
  const order = ui?.['ui:order'];
  if (!Array.isArray(order)) return keys;
  const known = order.filter((k): k is string => typeof k === 'string' && keys.includes(k));
  const rest = keys.filter((k) => !known.includes(k));
  return [...known, ...rest];
}

/** The ui-schema sub-node for a child key, tolerating a non-object `ui`. */
function uiChild(ui: UiSchema, key: string): UiSchema {
  const child = ui?.[key];
  return child && typeof child === 'object' ? (child as UiSchema) : undefined;
}

function isEnum(field: JsonSchema): boolean {
  return Array.isArray(field.enum) || Array.isArray(field.oneOf);
}

type EnumOption = { value: string; label: string };

/** Enum options, resolving labels via `oneOf` title, `enumNames`, else value. */
function enumOptions(field: JsonSchema): EnumOption[] {
  if (Array.isArray(field.oneOf)) {
    return field.oneOf.map((o) => ({
      value: String(o.const),
      label: o.title ?? String(o.const),
    }));
  }
  if (Array.isArray(field.enum)) {
    return field.enum.map((v, i) => ({
      value: String(v),
      label: field.enumNames?.[i] ?? String(v),
    }));
  }
  return [];
}

/** Whether a plain string field should render as a multi-line textarea. */
function isTextareaField(key: string, field: JsonSchema, ui: UiSchema): boolean {
  if (ui?.['ui:widget'] === 'textarea') return true;
  if (field.format === 'textarea') return true;
  return TEXTAREA_KEY_RE.test(key) || TEXTAREA_KEY_RE.test(field.title ?? '');
}

function uiString(ui: UiSchema, key: string): string | undefined {
  const value = ui?.[key];
  return typeof value === 'string' ? value : undefined;
}

const INPUT_CLASS =
  'h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80';

/** Renders one control for a single top-level (or nested) property. */
function Field({
  fieldKey,
  field,
  ui,
  value,
  required,
  error,
  disabled,
  depth,
  onChange,
}: {
  fieldKey: string;
  field: JsonSchema;
  ui: UiSchema;
  value: unknown;
  required: boolean;
  error?: string;
  disabled?: boolean;
  depth: number;
  onChange: (next: unknown) => void;
}) {
  const label = labelFor(fieldKey, field);
  const invalid = Boolean(error);
  const placeholder = uiString(ui, 'ui:placeholder');
  const help = uiString(ui, 'ui:help');
  const widget = uiString(ui, 'ui:widget');

  // Missing/unknown type degrades gracefully rather than throwing.
  const type = field.type;

  // Nested object → titled sub-section that recurses (depth-capped).
  if (type === 'object' && field.properties && depth < MAX_DEPTH) {
    const objValue = (value && typeof value === 'object' ? value : {}) as Record<string, unknown>;
    return (
      <section className="space-y-4 rounded-xl border border-border p-4">
        <h3 className="font-display text-sm font-medium text-foreground">
          {label}
          {required ? <span className="text-destructive"> *</span> : null}
        </h3>
        {field.description ? (
          <p className="text-xs text-muted-foreground">{field.description}</p>
        ) : null}
        <ObjectFields
          schema={field}
          ui={ui}
          value={objValue}
          disabled={disabled}
          depth={depth + 1}
          onChange={(nextObj) => onChange(nextObj)}
        />
      </section>
    );
  }

  // boolean → inline checkbox with the label.
  if (type === 'boolean') {
    return (
      <div className="space-y-1">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={Boolean(value)}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
            className="size-4 rounded border-input"
          />
          <span className="text-sm text-foreground">
            {label}
            {required ? <span className="text-destructive"> *</span> : null}
          </span>
        </label>
        {field.description ? (
          <p className="text-xs text-muted-foreground">{field.description}</p>
        ) : null}
        {help ? <p className="text-xs text-muted-foreground">{help}</p> : null}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </div>
    );
  }

  // Everything else shares the label + helper + error scaffolding.
  const control = (() => {
    // readOnly → show the value, not an input.
    if (field.readOnly) {
      const text =
        value === undefined || value === null || value === ''
          ? EM_DASH
          : typeof value === 'object'
            ? JSON.stringify(value)
            : String(value);
      return <div className="text-sm text-foreground">{text}</div>;
    }

    // string + enum/oneOf → native <select> styled like Input.
    if (type === 'string' && isEnum(field)) {
      const options = enumOptions(field);
      return (
        <select
          value={value === undefined || value === null ? '' : String(value)}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
          className={INPUT_CLASS}
        >
          <option value="">Select…</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      );
    }

    // string + date → native date input.
    if (type === 'string' && field.format === 'date') {
      return (
        <Input
          type="date"
          value={typeof value === 'string' ? value : ''}
          placeholder={placeholder}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
        />
      );
    }

    // number/integer → number input (parse to number; empty → undefined).
    if (type === 'number' || type === 'integer') {
      return (
        <Input
          type="number"
          value={value === undefined || value === null ? '' : String(value)}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') return onChange(undefined);
            const n = Number(raw);
            onChange(Number.isNaN(n) ? undefined : n);
          }}
        />
      );
    }

    // plain string → textarea / password per ui:widget, else single-line input.
    if (type === 'string') {
      const strValue = typeof value === 'string' ? value : '';
      if (widget === 'password') {
        return (
          <Input
            type="password"
            value={strValue}
            placeholder={placeholder}
            disabled={disabled}
            aria-invalid={invalid || undefined}
            onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
          />
        );
      }
      if (isTextareaField(fieldKey, field, ui)) {
        return (
          <Textarea
            rows={3}
            value={strValue}
            placeholder={placeholder}
            disabled={disabled}
            aria-invalid={invalid || undefined}
            onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
          />
        );
      }
      return (
        <Input
          type="text"
          value={strValue}
          placeholder={placeholder}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)}
        />
      );
    }

    // Unknown/missing type → read-only fallback, never crash.
    const text =
      value === undefined || value === null
        ? EM_DASH
        : typeof value === 'object'
          ? JSON.stringify(value)
          : String(value);
    return <div className="text-sm text-muted-foreground">{text}</div>;
  })();

  return (
    <label className="block space-y-1.5">
      <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </span>
      {control}
      {field.description ? (
        <span className="block text-xs text-muted-foreground">{field.description}</span>
      ) : null}
      {help ? <span className="block text-xs text-muted-foreground">{help}</span> : null}
      {error ? (
        <span className="block text-sm text-destructive" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  );
}

/** Renders every property of an object schema, wiring child changes back up. */
function ObjectFields({
  schema,
  ui,
  value,
  errors,
  disabled,
  depth,
  onChange,
}: {
  schema: JsonSchema;
  ui: UiSchema;
  value: Record<string, unknown>;
  errors?: Record<string, string>;
  disabled?: boolean;
  depth: number;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const keys = orderedKeys(schema, ui);
  const required = new Set(schema.required ?? []);
  return (
    <div className="space-y-4">
      {keys.map((key) => {
        const field = schema.properties![key];
        return (
          <Field
            key={key}
            fieldKey={key}
            field={field}
            ui={uiChild(ui, key)}
            value={value[key]}
            required={required.has(key)}
            error={errors?.[key]}
            disabled={disabled}
            depth={depth}
            onChange={(next) => {
              const nextValue = { ...value };
              if (next === undefined) delete nextValue[key];
              else nextValue[key] = next;
              onChange(nextValue);
            }}
          />
        );
      })}
    </div>
  );
}

export function SchemaForm({
  schema,
  uiSchema,
  value,
  onChange,
  errors,
  disabled,
  className,
}: {
  schema: JsonSchema;
  uiSchema?: UiSchema;
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  errors?: Record<string, string>;
  disabled?: boolean;
  className?: string;
}) {
  const keys = orderedKeys(schema, uiSchema);
  if (keys.length === 0) {
    return <p className="text-sm text-muted-foreground">No form fields to display.</p>;
  }
  return (
    <div className={cn('space-y-4', className)}>
      <ObjectFields
        schema={schema}
        ui={uiSchema}
        value={value}
        errors={errors}
        disabled={disabled}
        depth={0}
        onChange={onChange}
      />
    </div>
  );
}

/**
 * Lightweight validation for the common subset this form renders — NOT full
 * JSON-Schema validation. Per top-level field:
 * - `required` → must be present / non-empty.
 * - `string` `minLength` → length check when a value is present.
 * - `number`/`integer` → must be a finite number when present.
 * Returns a field→message map; an empty map means valid.
 */
export function validateSchemaForm(
  schema: JsonSchema,
  value: Record<string, unknown>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  const required = new Set(schema.required ?? []);
  const props = schema.properties ?? {};

  for (const key of Object.keys(props)) {
    const field = props[key];
    const v = value[key];
    const isEmpty = v === undefined || v === null || v === '';

    if (required.has(key) && isEmpty) {
      errors[key] = `${labelFor(key, field)} is required.`;
      continue;
    }

    if (isEmpty) continue;

    if (field.type === 'string' && typeof field.minLength === 'number') {
      if (typeof v === 'string' && v.length < field.minLength) {
        errors[key] = `${labelFor(key, field)} must be at least ${field.minLength} characters.`;
      }
    }

    if (field.type === 'number' || field.type === 'integer') {
      if (typeof v !== 'number' || !Number.isFinite(v)) {
        errors[key] = `${labelFor(key, field)} must be a number.`;
      }
    }
  }

  return errors;
}

/**
 * Starter form-field snippets for the JSON Schema editor's Examples tab.
 * Independently authored (not copied from the previous product's example
 * files). Insert merges each snippet into the current schema, UI settings,
 * and example data so designers can grow a form field by field.
 */

export type FormSchemaExample = {
  id: string;
  title: string;
  description: string;
  schema: Record<string, unknown>;
  ui: Record<string, unknown>;
  data: Record<string, unknown>;
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Deep-merge objects. Arrays in `required` are unioned; other arrays are replaced. */
export function mergeFormObjects(
  current: Record<string, unknown>,
  incoming: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...current };
  for (const [key, value] of Object.entries(incoming)) {
    const existing = out[key];
    if (key === 'required' && (Array.isArray(existing) || Array.isArray(value))) {
      const left = Array.isArray(existing) ? existing : [];
      const right = Array.isArray(value) ? value : [];
      out[key] = [...new Set([...left, ...right])];
      continue;
    }
    if (isPlainObject(existing) && isPlainObject(value)) {
      out[key] = mergeFormObjects(existing, value);
    } else {
      out[key] = value;
    }
  }
  return out;
}

function parseObject(text: string): Record<string, unknown> {
  try {
    const value = JSON.parse(text) as unknown;
    return isPlainObject(value) ? value : {};
  } catch {
    return {};
  }
}

export function prettyJson(value: Record<string, unknown>): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

export function insertExample(
  current: { schema: string; ui: string; data: string },
  example: FormSchemaExample,
): { schema: string; ui: string; data: string } {
  return {
    schema: prettyJson(mergeFormObjects(parseObject(current.schema), example.schema)),
    ui: prettyJson(mergeFormObjects(parseObject(current.ui), example.ui)),
    data: prettyJson(mergeFormObjects(parseObject(current.data), example.data)),
  };
}

export const FORM_SCHEMA_EXAMPLES: FormSchemaExample[] = [
  {
    id: 'text',
    title: 'Text field',
    description: 'A required single-line string with a default and placeholder (givenName).',
    schema: {
      type: 'object',
      required: ['givenName'],
      properties: {
        givenName: {
          type: 'string',
          title: 'Given name',
          default: 'Ada',
        },
      },
    },
    ui: {
      givenName: {
        'ui:placeholder': 'Enter a given name',
        'ui:autofocus': true,
      },
    },
    data: {},
  },
  {
    id: 'textarea',
    title: 'Text area',
    description: 'A multi-line field for longer answers (notes).',
    schema: {
      type: 'object',
      properties: {
        notes: {
          type: 'string',
          title: 'Notes',
          description: 'Anything the next step should know.',
        },
      },
    },
    ui: {
      notes: {
        'ui:widget': 'textarea',
      },
    },
    data: {},
  },
  {
    id: 'checkbox',
    title: 'Checkbox',
    description: 'A boolean confirmation field (acknowledged).',
    schema: {
      type: 'object',
      properties: {
        acknowledged: {
          type: 'boolean',
          title: 'I acknowledge this request',
          default: false,
        },
      },
    },
    ui: {},
    data: {},
  },
  {
    id: 'date',
    title: 'Date',
    description: 'A date picker for a calendar day (requestedDate).',
    schema: {
      type: 'object',
      properties: {
        requestedDate: {
          type: 'string',
          format: 'date',
          title: 'Requested date',
        },
      },
    },
    ui: {
      requestedDate: {
        'ui:widget': 'date',
        'ui:help': 'Pick the preferred date for this request.',
      },
    },
    data: {},
  },
  {
    id: 'dropdown',
    title: 'Dropdown',
    description: 'A single-select list with a fixed set of options (decision).',
    schema: {
      type: 'object',
      properties: {
        decision: {
          type: 'string',
          title: 'Decision',
          enum: ['pending', 'approved', 'rejected'],
          enumNames: ['Pending', 'Approved', 'Rejected'],
        },
      },
    },
    ui: {},
    data: {},
  },
  {
    id: 'password',
    title: 'Password',
    description: 'A masked string with a minimum length (accessCode).',
    schema: {
      type: 'object',
      properties: {
        accessCode: {
          type: 'string',
          title: 'Access code',
          minLength: 3,
        },
      },
    },
    ui: {
      accessCode: {
        'ui:widget': 'password',
        'ui:help': 'At least 3 characters.',
      },
    },
    data: {},
  },
];

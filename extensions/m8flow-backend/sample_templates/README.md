# Sample Templates

Pre-built workflow templates that can be loaded into the database on startup.

## Templates included

| ZIP file | Description |
|----------|-------------|
| `single-approval-WFH-Request.zip` | Work-from-home single approval |


## Automatic loading via environment variable

Set `M8FLOW_LOAD_SAMPLE_TEMPLATES=true` in your `.env` file (or export it) before starting the backend:

```env
M8FLOW_LOAD_SAMPLE_TEMPLATES=true
```

On startup the backend will:

1. Scan this directory for `.zip` files.
2. Skip any template whose key already exists in the database (no duplicates).
3. Extract each ZIP file, store the contained files on the filesystem, and insert a row into the `m8flow_templates` table.
4. Templates are created as **PUBLIC** and **published**, so every user can see and use them immediately.
5. The default tenant (`M8FLOW_DEFAULT_TENANT_ID`, defaults to `default`) owns the templates.

Accepted truthy values: `true`, `1`, `yes`, `on` (case-insensitive).

The variable defaults to `false` so templates are never loaded unless you opt in.

## Manual import via the UI

If you prefer not to enable automatic loading, you can import templates one-by-one through the Templates UI:

1. Download the desired `.zip` file from this directory.
2. Open the M8Flow frontend and navigate to **Templates**.
3. Use the **Import** button and upload the ZIP.

# Sample Templates

Pre-built workflow templates that can be loaded into the M8Flow templates table. Each `.zip` file in this directory is a self-contained template containing BPMN diagrams and optional JSON form schemas.

## Loading Templates

### Option 1 -- Automatic loading on startup

Set the environment variable in your `.env` file:

```
M8FLOW_LOAD_SAMPLE_TEMPLATES=true
```

On the next server start the backend will scan this directory, extract every `.zip` file, and insert a row into `m8flow_templates` with `visibility=PUBLIC`, `is_published=true`, and `created_by=system`.

Templates that already exist (same `template_key` for the default tenant) are silently skipped, so this is safe to leave enabled across restarts.

### Option 2 -- Run the standalone script

If you prefer not to restart the server, run the loader script directly from the repo root:

```bash
python extensions/m8flow-backend/bin/load_sample_templates.py
```

This creates the Flask application context and loads all sample ZIPs in one shot. Duplicate templates are skipped automatically.

### Option 3 -- Manual import via the UI

1. Download the desired `.zip` file from this directory.
2. Open the M8Flow frontend and navigate to **Templates**.
3. Click **Import Template (ZIP)**.
4. Provide a name and visibility, then upload the ZIP.

## Adding New Sample Templates

1. Create a `.zip` file containing at least one `.bpmn` file. Optionally include `.json` (form schemas), `.dmn` (decision tables), or `.md` files.
2. Name the ZIP after the desired `template_key` (e.g. `my-workflow.zip` becomes key `my-workflow`, displayed as "My Workflow").
3. Drop it into this directory.


## Duplicate Handling

- Before inserting, the loader queries `m8flow_templates` by `template_key` + `m8f_tenant_id`.
- If a matching row exists, the ZIP is skipped with a log message.
- The database unique constraint `(m8f_tenant_id, template_key, version)` acts as a safety net.

## Included Templates

### basic-script-task.zip

Run a Python script task and display the results.

- `basic-script-task.bpmn`

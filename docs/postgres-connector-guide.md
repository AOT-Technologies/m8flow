# PostgreSQL Connector Guide

Complete guide for using the PostgreSQL connector in M8flow workflows.

---

## Overview

The `connector-postgres-v2` enables PostgreSQL database operations directly from M8flow BPMN workflows via Service Tasks. It supports table creation, data manipulation, and raw SQL execution.

**Repository:** [sartography/connector-postgres](https://github.com/sartography/connector-postgres)

---

## Installation

### 1. Add to connector-proxy-demo

Edit [`pyproject.toml`](file:///home/sonal-aot/Documents/GitHub/m8flow-sonal/connector-proxy-demo/pyproject.toml):

```toml
connector-postgres-v2 = {git = "https://github.com/sartography/connector-postgres.git"}

# Required dependency (not listed in connector's pyproject.toml)
psycopg2-binary = "^2.9.9"
```

### 2. Update lock file

```bash
cd connector-proxy-demo
poetry lock --no-update
```

### 3. Rebuild container

```bash
docker compose -f dev.docker-compose.yml up --build -d
```

### 4. Verify

```bash
curl http://192.168.1.89:7004/v1/commands | grep postgres_v2
```

---

## Available Commands

| Command                      | Description              |
| ---------------------------- | ------------------------ |
| `postgres_v2/CreateTableV2`  | Create a new table       |
| `postgres_v2/DropTableV2`    | Drop an existing table   |
| `postgres_v2/InsertValuesV2` | Insert rows into a table |
| `postgres_v2/SelectValuesV2` | Query rows from a table  |
| `postgres_v2/UpdateValuesV2` | Update existing rows     |
| `postgres_v2/DeleteValuesV2` | Delete rows from a table |
| `postgres_v2/DoSQL`          | Execute raw SQL queries  |

---

## Database Connection

All commands require a `database_connection_str` parameter in **psycopg2 format**:

```
dbname=DATABASE_NAME user=USERNAME password=PASSWORD host=HOST port=PORT
```

### Example (from your .env):

```
dbname=postgres user=postgres password=postgres host=192.168.1.89 port=1111
```

> [!IMPORTANT]
> Do not wrap the connection string in quotes when using it in M8flow Service Tasks.

---

## Command Details

### CreateTableV2

Creates a new PostgreSQL table with specified columns and data types.

**Parameters:**

| Parameter                 | Type | Required | Description                          |
| ------------------------- | ---- | -------- | ------------------------------------ |
| `database_connection_str` | str  | Yes      | PostgreSQL connection string         |
| `table_name`              | str  | Yes      | Name of table to create              |
| `schema`                  | dict | Yes      | Table schema with column definitions |

**Schema Format:**

```python
{
  "column_definitions": [
    {
      "name": "column_name",
      "type": "data_type"
    }
  ]
}
```

**Example: Create users table**

```python
# database_connection_str
dbname=postgres user=postgres password=postgres host=192.168.1.89 port=1111

# table_name
users

# schema
{"column_definitions": [{"name": "id", "type": "serial PRIMARY KEY"}, {"name": "name", "type": "varchar(255)"}, {"name": "email", "type": "varchar(255)"}, {"name": "phone", "type": "varchar(50)"}, {"name": "created_at", "type": "timestamp DEFAULT NOW()"}]}
```

**Supported PostgreSQL Data Types:**

- Numeric: `int`, `serial`, `bigint`, `decimal(10,2)`, `numeric`, `real`, `double precision`
- String: `varchar(n)`, `char(n)`, `text`
- Date/Time: `date`, `time`, `timestamp`, `interval`
- Boolean: `boolean`
- JSON: `json`, `jsonb`
- Arrays: `integer[]`, `text[]`

---

### InsertValuesV2

Insert one or more rows into an existing table.

**Parameters:**

| Parameter                 | Type | Required | Description                  |
| ------------------------- | ---- | -------- | ---------------------------- |
| `database_connection_str` | str  | Yes      | PostgreSQL connection string |
| `table_name`              | str  | Yes      | Target table name            |
| `schema`                  | dict | Yes      | Columns and values to insert |

**Schema Format:**

```python
{
  "columns": ["col1", "col2", "col3"],
  "values": [
    ["value1", "value2", "value3"],
    ["value4", "value5", "value6"]
  ]
}
```

**Example: Insert user from form**

Assuming you have a user registration form with fields: `name`, `email`, `phone`

```python
# database_connection_str
dbname=postgres user=postgres password=postgres host=192.168.1.89 port=1111

# table_name
users

# schema (using form variables - NO outer quotes!)
{"columns": ["name", "email", "phone"], "values": [[name, email, phone]]}
```

**Example: Insert multiple rows**

```python
{"columns": ["name", "email", "phone"], "values": [["John Doe", "john@example.com", "555-1234"], ["Jane Smith", "jane@example.com", "555-5678"]]}
```

---

### SelectValuesV2

Query rows from a table with optional WHERE clause.

**Parameters:**

| Parameter                 | Type | Required | Description                            |
| ------------------------- | ---- | -------- | -------------------------------------- |
| `database_connection_str` | str  | Yes      | PostgreSQL connection string           |
| `table_name`              | str  | Yes      | Table to query                         |
| `schema`                  | dict | Yes      | Columns to select and optional filters |

**Schema Format:**

```python
{
  "columns": ["col1", "col2"],
  "where": [
    ["column_name", "operator", value]
  ]
}
```

**Supported WHERE operators:** `=`, `!=`, `<`, `>`

**Example: Select all users**

```python
# schema
{"columns": ["id", "name", "email", "phone", "created_at"]}
```

**Example: Select specific user**

```python
# schema
{"columns": ["id", "name", "email"], "where": [["email", "=", "john@example.com"]]}
```

**Example: Select with numeric comparison**

```python
# schema
{"columns": ["id", "name"], "where": [["id", ">", 10]]}
```

**Response:**

The query result will be stored in the process variable. Access it using:

```python
response_variable
```

---

### UpdateValuesV2

Update existing rows in a table.

**Parameters:**

| Parameter                 | Type | Required | Description                        |
| ------------------------- | ---- | -------- | ---------------------------------- |
| `database_connection_str` | str  | Yes      | PostgreSQL connection string       |
| `table_name`              | str  | Yes      | Table to update                    |
| `schema`                  | dict | Yes      | Columns to update and WHERE clause |

**Schema Format:**

```python
{
  "columns": ["col1", "col2"],
  "values": ["new_value1", "new_value2"],
  "where": [
    ["column_name", "=", value]
  ]
}
```

**Example: Update user email**

```python
# schema
{"columns": ["email"], "values": ["newemail@example.com"], "where": [["name", "=", "John Doe"]]}
```

---

### DeleteValuesV2

Delete rows from a table.

**Parameters:**

| Parameter                 | Type | Required | Description                  |
| ------------------------- | ---- | -------- | ---------------------------- |
| `database_connection_str` | str  | Yes      | PostgreSQL connection string |
| `table_name`              | str  | Yes      | Table to delete from         |
| `schema`                  | dict | Yes      | WHERE clause (optional)      |

**Schema Format:**

```python
{
  "where": [
    ["column_name", "=", value]
  ]
}
```

**Example: Delete specific user**

```python
# schema
{"where": [["email", "=", "john@example.com"]]}
```

> [!CAUTION]
> If you omit the WHERE clause, ALL rows will be deleted!

---

### DropTableV2

Drop (delete) an entire table.

**Parameters:**

| Parameter                 | Type | Required | Description                  |
| ------------------------- | ---- | -------- | ---------------------------- |
| `database_connection_str` | str  | Yes      | PostgreSQL connection string |
| `table_name`              | str  | Yes      | Table to drop                |

**Example:**

```python
# database_connection_str
dbname=postgres user=postgres password=postgres host=192.168.1.89 port=1111

# table_name
users
```

> [!CAUTION]
> This permanently deletes the table and all its data!

---

### DoSQL

Execute arbitrary SQL commands.

**Parameters:**

| Parameter                 | Type | Required | Description                  |
| ------------------------- | ---- | -------- | ---------------------------- |
| `database_connection_str` | str  | Yes      | PostgreSQL connection string |
| `schema`                  | dict | Yes      | SQL command to execute       |

**Schema Format:**

```python
{
  "sql": "YOUR SQL COMMAND HERE"
}
```

**Example: Create table with custom SQL**

```python
# schema
{"sql": "CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, customer VARCHAR(255), total DECIMAL(10,2))"}
```

**Example: Complex query**

```python
# schema
{"sql": "SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.name"}
```

---

## Common Patterns

### Pattern 1: User Registration Flow

1. **Form Task:** Collect user data (name, email, phone)
2. **Service Task (CreateTableV2):** Ensure users table exists
3. **Service Task (InsertValuesV2):** Insert user data

### Pattern 2: Data Query and Update

1. **Service Task (SelectValuesV2):** Query existing data
2. **Script Task:** Process/validate data
3. **Service Task (UpdateValuesV2):** Update records

### Pattern 3: Cleanup

1. **Service Task (DeleteValuesV2):** Remove old records
2. **Service Task (DropTableV2):** Remove temporary tables

---

## Troubleshooting

### Syntax Error in schema parameter

**Error:** `SyntaxError: invalid syntax`

**Cause:** Wrapping JSON in quotes

**Solution:** Remove outer quotes from schema parameter

```python
# ❌ WRONG
"{\"columns\": [...]}"

# ✅ CORRECT
{"columns": [...]}
```

### Connection Failed

**Error:** Connection refused or timeout

**Solution:**

- Verify database is running and accessible
- Check host/port in connection string
- Ensure firewall allows connection from container

### Module not found: psycopg2

**Error:** `ModuleNotFoundError: No module named 'psycopg2'`

**Solution:** Add to `pyproject.toml`:

```toml
psycopg2-binary = "^2.9.9"
```

### Table already exists

**Error:** `relation "table_name" already exists`

**Solution:**

- Use `DoSQL` with `CREATE TABLE IF NOT EXISTS`
- Or drop table first with `DropTableV2`

---

## PostgreSQL Configuration

Your current setup (from `.env`):

```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=postgres
```

**Connection string for M8flow:**

```
dbname=postgres user=postgres password=postgres host=192.168.1.89 port=1111
```

---

## Example BPMN Workflow

### Complete User Registration Example

**Process:** `postgres-test.bpmn`

**Tasks:**

1. **Start Event**
2. **User Task** - "Registration Form"
   - Form: `user-registration-schema.json`
   - Collects: name, email, phone
3. **Service Task** - "Create Users Table"
   - Operator: `postgres_v2/CreateTableV2`
   - Parameters: See CreateTableV2 example above
4. **Service Task** - "Insert User to Database"
   - Operator: `postgres_v2/InsertValuesV2`
   - Parameters: See InsertValuesV2 example above
5. **End Event**

---

## Reference Links

- [PostgreSQL Data Types](https://www.postgresql.org/docs/current/datatype.html)
- [Connector Repository](https://github.com/sartography/connector-postgres)
- [Connector Setup Guide](./connector-setup-guide.md)

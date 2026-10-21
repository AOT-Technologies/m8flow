# Roles and permissions

This page lists what each role can do. The source of truth is the permission
policy in `m8flow-backend/src/m8flow_backend/config/permissions/m8flow.yml`,
which the backend loads into the database when a user signs in.

## Roles

Each role grants a fixed set of permissions:

| Role | Scope | Summary |
|---|---|---|
| `super-admin` | Platform | Tenant registry, invitations, and read access across tenants |
| `tenant-admin` | One tenant | Everything inside the tenant, including members, groups, and API keys |
| `editor` | One tenant | Design process models and templates, and run and control instances |
| `integrator` | One tenant | Manage secrets and connector profiles |
| `reviewer` | One tenant | Work assigned tasks in **Task Review** |
| `submitter` | One tenant | Start processes and submit assigned tasks |
| `viewer` | One tenant | Read-only access |

Every signed-in user also belongs to the `everybody` group, which grants basic
access such as reading their own session and onboarding data.

## Capabilities by role

In the following table, **Yes** means full access, **Read** means read-only
access, and **No** means no access.

| Capability | super-admin | tenant-admin | editor | integrator | reviewer | submitter | viewer |
|---|---|---|---|---|---|---|---|
| View process groups and models | Read | Read | Read | No | Read | Read | Read |
| Create and edit process groups and models | Yes | Yes | Yes | No | No | No | No |
| Start a process | Yes | Yes | Yes | No | No | Yes | No |
| View process instances | Read | Read | Read | No | No | Read | Read |
| Suspend, resume, retry, terminate, or delete an instance | No | Yes | Yes | No | No | No | No |
| Work and complete tasks | Read | Yes | Yes | No | Yes | Yes | Read |
| Manage templates | No | Yes | Yes | No | No | No | No |
| View templates | Read | Read | Read | No | No | No | Read |
| Manage secrets | Yes | Yes | No | Yes | No | No | No |
| View secret keys | Read | Read | No | Read | No | No | Read |
| Manage connector profiles | Yes | Yes | No | Yes | No | No | No |
| View connector profiles | Read | Read | Read | Read | Read | Read | Read |
| Manage messages and data stores | No | Yes | Yes | No | No | No | No |
| Manage tenant members and groups | Yes | Yes | No | No | No | No | No |
| Manage the tenant registry and invitations | Yes | No | No | No | No | No | No |
| Manage API keys | No | Yes | No | No | No | No | No |
| View API keys and trigger events | Read | Read | No | No | No | No | No |
| Use the **MCP Tools** page | Yes | Yes | No | No | No | No | No |
| View the **MCP Connection** page | Yes | Yes | Yes | Yes | No | No | No |
| View NATS streams and consumers | Read | No | No | No | No | No | No |

## How a role reaches a user

A user gets tenant roles through groups:

1. A tenant-admin adds the user to a group in the tenant, in **Tenant
   Management** > **Groups**, or in the Keycloak organization.
2. Each group maps to one or more roles.
3. At sign-in, and when the user's memberships change, the backend syncs the
   user's tenant-qualified groups, for example `acme:editor`.

The bootstrap creates these organization groups and role mappings in the
default organization:

| Organization group | Role |
|---|---|
| Administrators | `tenant-admin` |
| Designers | `editor` |
| Support | `integrator` |
| Approvers | `reviewer` |
| Submitters | `submitter` |
| Viewers | `viewer` |

## Permission entries

Each entry in `m8flow.yml` has the following fields:

| Field | Meaning |
|---|---|
| `groups` | Roles that receive the permission |
| `actions` | Any of `read`, `create`, `update`, `delete`, `start`, `execute`, or `all` |
| `uri` | The API path pattern, without the `/v1.0` prefix. `*` matches the rest of the path. `PG:ALL` and `PM:ALL` expand to every process group and every process model. |

The following entry lets editors and tenant-admins manage every process
model:

```yaml
manage-all-process-models:
  groups: ["tenant-admin", "editor", "super-admin"]
  actions: [all]
  uri: PM:ALL
```

Changes to `m8flow.yml` take effect at each user's next sign-in. The backend
adds permissions from the file but doesn't remove them, so remove a permission
from the database as well as from the file.

## Related pages

- [About multi-tenancy and access control](../explanation/multi-tenancy-and-access.md)
- [Manage tenants and members](../how-to/manage-tenants-and-members.md)

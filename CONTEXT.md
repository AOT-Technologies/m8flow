# M8Flow

Host for running and cataloguing BPMN process models. This glossary is the shared language for catalog and runtime concepts — not an implementation spec.

## Language

**Process model**:
A named BPMN definition and its accompanying files in a tenant catalog.
_Avoid_: process (alone), process instance, workflow, edit process instance

**Process instance**:
One execution of a process model.
_Avoid_: process (alone), run (as the noun for the entity), process model

**Process-model overview**:
The designer page for one process model: identity, stats, recent instances, and files. It is not the canvas that edits BPMN or forms.
_Avoid_: edit process instance page, process instance page, ProcessModelShow, modeler

**Process modeler**:
The canvas for editing a process model's BPMN, DMN, form schema files, and markdown files.
_Avoid_: overview, editor (alone)

**Process instance detail**:
The designer page for one process instance: identity, metadata, Tasks I can complete, and tabs. It is not the process-model overview and not only the diagram canvas.
_Avoid_: process instance page, ProcessInstanceShow, events page

**Tasks I can complete**:
The list on process instance detail of incomplete human tasks the current user is a candidate for. Distinct from every open task on the instance and from the approval chain.
_Avoid_: My tasks as this table, all open tasks, approval chain

**Task title**:
The display name of a human task. Shown as the Task column on Tasks I can complete, on the Tasks tab, and on Home My tasks. Distinct from the BPMN identifier and from who owns or completed the task.
_Avoid_: name as the owner, task name as the only label when a title exists

**Completed by**:
The person who completed a human task. Shown on the Tasks tab. Distinct from Task title and from the approval-chain owner name.
_Avoid_: owner, name as the Task column

**Waiting for**:
On Tasks I can complete, the BPMN lane the human task sits in. Not the candidate username.
_Avoid_: assignee, waiting on as a person

**Process instance viewer**:
The read-only canvas on process instance detail that shows one process instance's diagram, including live task-state.
_Avoid_: modeler, current events, events page, ReactDiagramEditor

**Process instance event**:
A recorded change on a process instance (task completed, instance suspended, and the like). The Events tab on process instance detail lists these. Distinct from BPMN Messages.
_Avoid_: activity as the entity, current events, message

**Terminate**:
Ending a process instance so it cannot continue. Distinct from suspend.
_Avoid_: cancel, kill, delete the instance

**Suspend**:
Pausing a live process instance. Distinct from terminate.
_Avoid_: pause as a separate product action, hold

**Resume**:
Continuing a suspended process instance. Distinct from retry (recovering an errored instance).
_Avoid_: restart, retry, unpause as a separate product action

**Last milestone**:
The name currently stored on a process instance. Core stamps it when the instance starts from the process definition's BPMN name (or identifier). It is not a history of reached checkpoints.
_Avoid_: milestone history, current milestone as a second field, event

**Revision**:
The metadata-grid slot on process instance detail for a process-model version. This product does not use git for that, so the slot stays empty (`—`). Distinct from Last milestone.
_Avoid_: (git), git commit, content hash as this label

**Properties panel**:
The side panel of element fields shown while designing a process model (or a DMN file).
_Avoid_: inspector, attributes panel, settings

**Form schema file**:
A JSON Schema file in a process model that a user task binds to, with optional companion UI-schema and example-data files.
_Avoid_: form builder, RJSF builder, form (alone)

**Catalog**:
The tenant's tree of process groups and process models.
_Avoid_: templates gallery, process instances, connector catalog

**Process group**:
A folder of process models in a tenant catalog.
_Avoid_: folder, directory, tenant

**Created by**:
The user who created a catalog object (process model or template). The mockup label "Owner" is this person, not a separate role.
_Avoid_: owner

**Shared realm**:
The Keycloak realm where tenant users authenticate. Organizations in this realm map to tenants.
_Avoid_: spoke realm, tenant realm

**Master realm**:
The Keycloak realm for platform / super-admin sign-in.
_Avoid_: admin realm, spoke realm

**Active tenant**:
The organization a shared-realm user is working in for the current session.
_Avoid_: localStorage tenant, selected tenant as a browser-storage value

**Tenant selection gate**:
The post-login step that chooses the active tenant when a shared-realm user belongs to organizations. It is not the tenant registry or tenant admin.
_Avoid_: Tenants page, All Tenants, tenant switcher

**Tenant registry**:
The platform list of tenants (id, name, slug, status) that a super-admin manages. It is not the tenant selection gate, the tenant switcher, or tenant admin.
_Avoid_: All Tenants as the entity, tenant-admin, Tenant Management

**Tenant admin**:
The per-tenant surface for members, groups, and role grants. A tenant-admin uses it for the active tenant; a super-admin can use it for any tenant. It is not the tenant registry, tenant selection gate, or tenant switcher.
_Avoid_: Tenants page, All Tenants, tenant-admin as the tenant registry

**Tenant switcher**:
The super-admin shell control that filters which tenant's data is shown (all tenants vs one). It does not set the active-tenant cookie.
_Avoid_: tenant selection gate, selected tenant as a browser-storage value

**Accept invitation**:
The public path where an invited person sets a password and becomes a shared-realm user in an organization. Distinct from creating, resending, or revoking invitations. The emailed URL uses the designer origin.
_Avoid_: invitation admin, tenant invite UI

**Invitation management**:
The super-admin path that creates, lists, resends, and revokes invitations for a tenant. Distinct from Accept invitation. A tenant-admin cannot do this.
_Avoid_: Accept invitation, tenant invite UI as the public path

**Service account**:
A tenant-scoped machine credential for API access, not a human Keycloak login.
_Avoid_: NATS API key, manage-token, spoke-realm client

**Secret**:
A tenant-scoped named credential stored by the host. After create, the value is never shown again on list or show.
_Avoid_: environment variable, service account, NATS API key, Keycloak client secret

**Secret key**:
The `\w+` name of a secret (for example `SMTP_PASSWORD`). It is not the value and not the internal numeric id.
_Avoid_: secret name as a display title, secret id as what the user types

**Secret sentinel**:
The BPMN and Jinja token `M8FLOW_SECRET:<secret key>` that the host replaces with the stored value at runtime.
_Avoid_: SPIFF_SECRET, env-var interpolation

**Secret backend**:
The store that holds secret values for a tenant: the Postgres `secret` table by default, or HashiCorp Vault KV v2 when enabled.
_Avoid_: connector proxy, Keycloak

**Configuration**:
The designer Setup surface whose product job is secrets (list, create, show, update, delete). It is not Authentications, Connectors, or tenant admin.
_Avoid_: settings, preferences, Authentications

**Connectors**:
The designer Setup surface for connector families, their operations, and their profiles. Distinct from Configuration (secrets) and from the process modeler properties panel.
_Avoid_: connector catalog, Authentications, Configuration, HTTP Connector canvas

**Connector family**:
A group of service-task operators that share one prefix (for example `http`). Distinct from one operator and from a connector profile.
_Avoid_: connector (alone), operator, canvas

**Connector profile**:
A named, tenant-scoped configuration for one connector family. For HTTP it holds optional basic-auth only. Distinct from Secret and from the task-only parameters on a Service Task (URL, headers, query, body).
_Avoid_: secret, connector config as a secret, configuration as this entity, Bearer as a profile field

**HTTP connector**:
The `http` connector family: the six `http/*RequestV2` operators plus HTTP profiles. Not SMTP, Slack, Postgres, or other families.
_Avoid_: HTTP Connector canvas, canvas as this product, connector (alone)

**m8flow_profile**:
The Service Task parameter whose value is a connector profile's `profile_name`. The host removes it at execute so it never reaches the proxy.
_Avoid_: profile as this parameter, secret sentinel as this binding

**Template**:
A reusable pack of BPMN and accompanying files, versioned under a key, stored outside the catalog. Distinct from a process model.
_Avoid_: process model, connector template, Keycloak realm template

**Template gallery**:
The designer page that lists templates for the active tenant.
_Avoid_: catalog, templates as the catalog tree

**Template modeler**:
The canvas for editing a template's BPMN, DMN, form schema files, and markdown files. Distinct from the process modeler, which edits a catalog process model.
_Avoid_: process modeler as this page, template editor (alone)

**Template publish**:
The one-way freeze of a draft template version so it can be used to create a process model. There is no unpublish; further edits create a new draft version.
_Avoid_: unpublish, visibility as this action, save as publish

**Save as template**:
Creating a new template from a process model's files. Distinct from Import ZIP and from a blank New template.
_Avoid_: export, copy, New template as this path

**Create process model from template**:
Instantiating a published template version as a new process model in the catalog.
_Avoid_: import, copy process model, use template as the entity

**Template version**:
One stored edition of a template key (`V1`, `V2`, …). Editing a published version creates a new draft version. Distinct from Revision on process instance detail.
_Avoid_: revision, git version

**Created from template**:
The process-model overview record that a process model was instantiated from a template version.
_Avoid_: provenance as the user-facing label, owner, template-info as the entity

**Template visibility**:
PUBLIC, TENANT, or PRIVATE — who can see a template. Distinct from whether the version is published, and from RBAC groups.
_Avoid_: published as this field, permission as this field

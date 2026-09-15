# Permanently dropped HTTP surfaces after the m8flow-bpmn-core cutover.
#
# These routes are absent from the unified OpenAPI spec. Clients receive 404.
#
# - Messaging / correlation (`/v1.0/messages`, message instance APIs)
# - Call-activity lookup (`/v1.0/process-models/.../callers` and related)
# - BPMN data stores (`json_data_store`, `kkv_data_store`)
# - Saved process-instance reports
# - Process-instance queue / Celery run-task preflight
#
# Disposition (08 unclassified-file table): covered and already-m8flow-owned
# files stay on Identity / Auth / Authorization / Catalog / Human Task /
# Workflow operations / Secrets. Gap files for messaging, call-activity, and
# data stores remain dropped. Host rebuild rows map to those eight modules.
# No new dispositions.

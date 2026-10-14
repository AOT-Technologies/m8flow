# Upstream corpus recovery pin

The SpiffArena vendor folders (`spiffworkflow-backend/`, `spiffworkflow-frontend/`,
`spiff-arena-common/`) were never in this repository's git history. They were
fetched from:

- URL: `https://github.com/AOT-Technologies/m8flow-core.git`
- Ref: `1.0.0`
- Folders: `spiffworkflow-backend`, `spiff-arena-common`, `spiffworkflow-frontend`

Do not repurpose copy/CPD license gates against `m8flow-bpmn-core` source.
The runtime pin for this cutover is the local `m8flow-bpmn-core` `0.2.1` wheel.

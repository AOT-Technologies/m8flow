# m8flow-frontend

Apache-2.0 React/Vite UI package (legacy Spiff-derived surface). For the primary
designer experience, prefer [`m8flow-designer/`](../m8flow-designer/).

## What lives here

```text
m8flow-frontend/
|-- src/                              Components, views, hooks, and services
|-- package.json                      Frontend package definition
|-- vite.config.ts                    Vite config for local dev and builds
|-- tsconfig.json                     TypeScript config
`-- ARCHITECTURE.md                   Design notes
```

## Development workflow

```bash
cd m8flow-frontend
npm ci
npm run start
```

Build / test:

```bash
npm run build
npm test
```

No SpiffArena vendor fetch step is required — this package is self-contained.

## Related docs

- Repo root setup guide: `README.md`
- Designer UI: `m8flow-designer/README.md`
- Known gaps: `docs/known-gaps.md`

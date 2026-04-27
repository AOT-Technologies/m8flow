# m8flow-frontend

Apache-2.0 **m8flow-specific frontend layer** implemented as a standalone React/Vite application. It extends the upstream UI (`spiffworkflow-frontend`) without modifying upstream files.

## License boundary (important)

Upstream `spiffworkflow-frontend/` is fetched into the repo root at development/build time and is gitignored to keep the Apache-2.0 layer clean.

Fetch upstream folders when needed:

- Bash: `./bin/fetch-upstream.sh`
- PowerShell: `.\bin\fetch-upstream.ps1`

## What lives here

```text
m8flow-frontend/
|-- src/                              Extension components, views, hooks, and services
|-- package.json                      Frontend package definition
|-- vite.config.ts                    Vite config for local dev and builds
|-- vite-plugin-override-resolver.ts  Override resolution for upstream imports
|-- tsconfig.json                     TS path mappings for upstream imports
`-- ARCHITECTURE.md                   Detailed override/resolution design
```

## Development workflow

1. Fetch upstream folders once after cloning:

```bash
./bin/fetch-upstream.sh
```

```powershell
.\bin\fetch-upstream.ps1
```

2. Install dependencies:

```bash
cd m8flow-frontend
npm ci
```

3. Run the dev server:

```bash
npm run start
```

Other useful commands:

- `npm run build`
- `npm run test`
- `npm run typecheck`

## How overrides work (high level)

- Import core modules via the alias `@spiffworkflow-frontend/*` (configured in `vite.config.ts` and `tsconfig.json`).
- If an override exists in `m8flow-frontend/src/**`, the Vite override resolver prefers it.
- If no override exists, resolution falls back to the upstream `spiffworkflow-frontend/src/**` module.

For details (including the resolver rules), see `m8flow-frontend/ARCHITECTURE.md`.

## Related docs

- Repo root setup guide: `README.md`
- Environment variables: `docs/env-reference.md`
- Frontend override architecture: `m8flow-frontend/ARCHITECTURE.md`


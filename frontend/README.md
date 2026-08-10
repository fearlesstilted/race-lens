# Race Lens frontend

React + TypeScript broadcast UI for the Race Lens replay and near-live API.

The browser does not parse local JSONL fixtures. It requests reconstructed
state from FastAPI, subscribes to SSE streams, and renders the timing tower,
track map, race feed, insights, highlights, and experimental strategy views.

## Development

Start the backend on port `8000`, then:

```bash
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to
`http://localhost:8000`; set `RACELENS_API_TARGET` to use another backend.

## Checks

```bash
npm run build
npm run lint
```

The API contract is defined by the backend at http://localhost:8000/docs.

## Windows desktop

The Tauri shell keeps the same UI and workspace settings. Development uses the
local Vite/API setup; packaged builds use `https://race-lens.onrender.com`:

```bash
npm run tauri dev
npm run tauri build
```

Pushing a `desktop-v*` tag builds an unsigned Windows x64 NSIS installer and
opens a draft GitHub release. Windows SmartScreen may warn until code signing
is added; verify the GitHub release and publisher before running it. Signing,
automatic updates, ARM64, an offline backend, and embedded recording are
deliberately not included.

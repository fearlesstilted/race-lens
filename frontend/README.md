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

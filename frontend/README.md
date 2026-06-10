# Race Lens Frontend

Vite + React timing monitor for replaying a static Race Lens JSONL event timeline.

## Local Data

Generate the Monaco fixture from the backend:

```bash
cd ../backend
python -m racelens.cli ingest 2024 Monaco R -o fixtures/monaco_2024_race.jsonl
```

Expose it to Vite:

```bash
mkdir -p public/fixtures
cp ../backend/fixtures/monaco_2024_race.jsonl public/fixtures/
```

## Run

```bash
npm install
npm run dev
```

The frontend currently reconstructs replay state in the browser from JSONL. Once the FastAPI
`/state` endpoint is ready, replace the local replay call with API reads and keep the same table
state shape.

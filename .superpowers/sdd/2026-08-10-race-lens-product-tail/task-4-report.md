# Task 4 report: Official DOTD and measured Whisper improvement

## Status

Complete. Official Formula 1 fan-vote results are parsed from Next structured
records, strictly validated against exact normalized meetings and replay drivers,
stored separately from replay manifests, exposed only for finished replays, and
rendered distinctly from local and Race Lens picks.

The private radio evaluator accepts exactly 50 bounded local JSONL records and
compares the required three Whisper profiles with WER, F1 keyword accuracy,
latency, and explicit default gates. Production remains `medium`/`int8`; newly
written transcript event payloads include model/profile/version metadata.

## Checks

- Focused backend: `27 passed in 14.44s`.
- Focused frontend: `DOTD result ordering check passed`.
- Changed Python files: `ruff` passed.
- Changed TypeScript/TSX files: `eslint` passed.
- No Whisper model, network audio, private reference manifest, or full matrix was run.

## Concerns

- No private 50-clip dataset is present, so no evidence supports changing the
  production Whisper default. The CLI reports eligibility but never rewrites the
  configured default.
- Formula 1 may publish an award after archive completion. Publication remains
  successful; the private recorder retries missing completed-race awards every
  six hours and all absent, malformed, wrong-event, or ambiguous data stays null.

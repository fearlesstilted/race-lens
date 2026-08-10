# Task 7 report: Tauri Windows shell

## Status

The existing React app now has a minimal Tauri 2 desktop shell. Web builds keep
relative `/api` URLs; desktop builds use the production Render API through one
URL helper. FastAPI CORS is restricted to the production web app, packaged
Tauri origins, and local Vite development.

A tag-only GitHub workflow builds an unsigned Windows x64 NSIS installer into a
draft release. The shell does not embed Python, fixtures, recording, Whisper,
an updater, or an offline backend.

## Focused verification

- `npm run check:desktop`
- `npm run build:desktop`
- `cargo metadata --manifest-path frontend/src-tauri/Cargo.toml --no-deps`
- `git diff --check`

## Limitations

- The Linux host resolved the Rust manifest/lockfile but cannot produce the
  Windows NSIS artifact; `cargo check` reached native shell dependencies but stopped
  because this host lacks GTK/GDK development libraries. The tag workflow
  builds and bundles against the intended MSVC target on `windows-latest`.
- The installer is unsigned, so Windows SmartScreen can warn until signing is
  funded and configured.

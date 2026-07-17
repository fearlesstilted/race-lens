# Automated recorder

The Debian worker records every Formula 1 session from FP1 through the race.
It starts ten minutes before the published UTC time, resumes an interrupted
capture, rejects stale or mismatched SignalR sessions, and keeps raw recordings
for recovery. After the archive becomes available it builds the canonical
fixture, merges captured team radio, transcribes it with Whisper, and generates
track telemetry for sessions selected for publication.

By default every session is archived on the server, while races and sprints are
published to the demo. Change `RECORDER_PUBLISH_SESSIONS` in the private env
file to alter that policy.

## Install or update

From the server checkout:

```sh
deploy/recorder/install.sh
```

No Compose or sudo is required. The script replaces only the container named
`race-lens-recorder` and never publishes a port. State lives outside Git:

- `~/.config/race-lens-recorder/recorder.env`
- `~/.local/share/race-lens-recorder/data/`
- `~/.local/share/race-lens-recorder/state/`
- `~/.local/share/race-lens-recorder/raw/`

The installer also adds a two-minute host watchdog. Health requires a recent
worker heartbeat and, during capture, a growing raw feed. An unhealthy
container is restarted and resumes the same recording by appending.

## Publication boundary

The container has no repository or SSH key. It can only write an exact fixture,
track, and positions triplet to the staging directory. `publish.py` runs on the
host, validates names, paths, sizes, and the exact file set, then pushes a
single `capture/*` branch. GitHub Actions validates the archive and runs the
full backend, Rust, and frontend checks before fast-forwarding `main`.

This separation means a parser or media dependency compromised inside the
container cannot use Git credentials. The host publisher must be installed by
the operator with its own write-enabled deploy key and cron entry.

## Container security

The worker runs as the caller's non-root UID/GID with all capabilities dropped,
`no-new-privileges`, a read-only root filesystem, a no-exec `/tmp`, and CPU,
memory, PID, and descriptor limits. Only `data`, `state`, and `raw` are writable.
Docker's default seccomp and AppArmor profiles remain active. The bridge network
allows outbound F1/FastF1/model traffic; there are no inbound ports.

Docker daemon access remains root-equivalent on the host. This deployment does
not pretend otherwise.

## Checks

```sh
docker inspect race-lens-recorder --format \
  'user={{.Config.User}} status={{.State.Status}} health={{.State.Health.Status}} readonly={{.HostConfig.ReadonlyRootfs}}'
docker port race-lens-recorder          # must print nothing
docker logs --tail 100 race-lens-recorder
python3 deploy/recorder/publish.py      # normally invoked by cron
```
